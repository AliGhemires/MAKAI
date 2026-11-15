"""The tidy-up mission as a state machine.

    SEARCH -> APPROACH -> PICK -> FIND_STATION -> GO_TO_STATION -> DROP -> BACK_OFF -> SEARCH ...
    SEARCH (nothing in sight, far from the start) -> RETURN_HOME -> SEARCH -> DONE

It only talks to the contracts in `makai.contracts`, so it runs unchanged on the
simulator and on the real robot. All timing uses observation stamps, never wall-clock.
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from makai.contracts import (
    BaseVelocity,
    Category,
    DropSkill,
    Perception,
    PickSkill,
    Robot,
    Scene,
    Target,
)
from makai.navigation.approach import ApproachConfig, ApproachController
from makai.navigation.odometry import MAX_GAP_S, Odometry

log = logging.getLogger("makai.mission")


class State(StrEnum):
    SEARCH = "search"
    SWEEP = "sweep"  # the three states of the sweeping mission (orchestrator/sweep.py)
    DOCK = "dock"
    RESUME = "resume"
    APPROACH = "approach"
    PICK = "pick"
    FIND_STATION = "find_station"
    GO_TO_STATION = "go_to_station"
    DROP = "drop"
    BACK_OFF = "back_off"
    RETURN_HOME = "return_home"
    DONE = "done"
    FAILED = "failed"


TERMINAL = (State.DONE, State.FAILED)


@dataclass(frozen=True)
class MissionConfig:
    approach: ApproachConfig = field(default_factory=ApproachConfig)
    station_standoff_m: float = 0.35  # where to stop in front of a station
    station_tol_m: float = 0.03
    search_speed: float = 0.6  # rad/s
    search_turns: float = 1.25  # turns without seeing anything => the room is clean
    lost_timeout_s: float = 1.5  # how long a tracked point may disappear
    # Close to the robot the object leaves the front camera's view. Below this distance we keep
    # going on odometry alone ("last mile"), for at most `blind_timeout_s`.
    blind_below_x_m: float = 0.45
    blind_timeout_s: float = 8.0
    approach_timeout_s: float = 40.0
    track_gate_m: float = 0.30  # max jump between two sightings of the same object
    station_exclusion_m: float = 0.30  # ignore objects this close to a station (already delivered)
    max_pick_attempts: int = 3  # per object, from each side tried
    # Then go round the object and try from another side: so many degrees round it from where the
    # first approach came (counter-clockwise seen from above), one after the other. () = give up.
    orbit_deg: tuple[float, ...] = (40.0, -40.0)
    orbit_radius_m: float = 0.50  # back away to this distance first: the camera sees the object again
    orbit_speed: float = 0.3  # rad/s, the base's turn while it goes round
    max_failed_objects: int = 3  # consecutive objects abandoned before giving up
    max_drop_attempts: int = 2
    back_off_speed: float = 0.10  # m/s
    back_off_s: float = 1.5
    home_radius_m: float = 0.25  # 'at home' = this close to where the mission started


@dataclass
class MissionStats:
    picked: int = 0
    delivered: int = 0
    failed_picks: int = 0
    abandoned: int = 0


@dataclass(frozen=True)
class Event:
    stamp: float
    previous: State
    state: State
    reason: str


class Mission:
    def __init__(
        self,
        robot: Robot,
        perception: Perception,
        pick: PickSkill,
        drop: DropSkill,
        cfg: MissionConfig | None = None,
        on_event: Callable[[Event], None] | None = None,
    ):
        self.robot, self.perception, self.pick, self.drop = robot, perception, pick, drop
        self.cfg = cfg or MissionConfig()
        self.on_event = on_event
        self.state = State.SEARCH
        self.stats = MissionStats()
        self.events: list[Event] = []
        self.carrying: Category | None = None
        self.scene = Scene()
        self.now = 0.0

        self._object_ctrl = ApproachController(self.cfg.approach)
        self._station_ctrl = ApproachController(
            replace(
                self.cfg.approach,
                goal_x_m=self.cfg.station_standoff_m,
                goal_y_m=0.0,
                tol_x_m=self.cfg.station_tol_m,
                tol_y_m=self.cfg.station_tol_m,
            )
        )
        self._home_ctrl = ApproachController(
            replace(
                self.cfg.approach,
                goal_x_m=0.0,
                goal_y_m=0.0,
                tol_x_m=self.cfg.home_radius_m / 2,
                tol_y_m=self.cfg.home_radius_m / 2,
                settle_ticks=1,
            )
        )
        self.odometry = Odometry()
        self._track: Target | None = None
        self._entered: float | None = None
        self._last_seen = 0.0
        self._prev_stamp: float | None = None
        self._pick_attempts = 0
        self._drop_attempts = 0
        self._failed_objects = 0
        self._reset_orbit()

    # ------------------------------------------------------------------ loop

    def step(self) -> State:
        """One control tick: observe, perceive, act."""
        obs = self.robot.get_observation()
        self.scene = self.perception.perceive(obs)
        now = self.now = obs.stamp
        self.odometry.update(obs.base_velocity, now)
        self._predict_track(obs.base_velocity, now)
        if self._entered is None:
            self._entered = self._last_seen = now
        getattr(self, f"_on_{self.state.value}")(self.scene, now)
        return self.state

    def run(self, max_duration_s: float = 600.0, rate_hz: float | None = None) -> State:
        """Run until done. `rate_hz` paces the loop on a real robot; leave None in simulation."""
        start: float | None = None
        try:
            while self.state not in TERMINAL:
                tick = time.perf_counter()
                self.step()
                start = self.now if start is None else start
                if self.now - start > max_duration_s and self.state not in TERMINAL:
                    self._go(State.FAILED, self.now, "mission timeout")
                if rate_hz:
                    time.sleep(max(0.0, 1.0 / rate_hz - (time.perf_counter() - tick)))
        finally:
            self.robot.stop()
        return self.state

    # ---------------------------------------------------------------- states

    def _on_search(self, scene: Scene, now: float) -> None:
        if self._start_approach(scene, now):
            return
        self.robot.drive(BaseVelocity(theta=self.cfg.search_speed))
        if (now - self._entered) * self.cfg.search_speed > self.cfg.search_turns * 2 * math.pi:
            if self.odometry.distance_from_home > self.cfg.home_radius_m:
                self._home_ctrl.reset()
                self._go(State.RETURN_HOME, now, "nothing in sight here, going back to the start")
            else:
                self._go(State.DONE, now, "nothing left on the floor")

    def _on_return_home(self, scene: Scene, now: float) -> None:
        if self._start_approach(scene, now):
            return
        velocity, arrived = self._home_ctrl.step(*self.odometry.home_in_base())
        self.robot.drive(velocity)
        if arrived or now - self._entered > self.cfg.approach_timeout_s:
            self.odometry = Odometry()  # search from here; do not come back again
            self._go(State.SEARCH, now, "back at the start")

    def _on_approach(self, scene: Scene, now: float) -> None:
        match = self._match_track(scene)
        if match is not None:
            if match.confidence <= 0.0 < self._track.confidence:
                # A guess from far away must not overwrite what we already know it is.
                match = replace(match, category=self._track.category, confidence=self._track.confidence)
            self._track, self._last_seen = match, now
        elif (
            not self._orbit_left  # going round it: followed on odometry, it shows again at the end
            and not self._in_blind_zone(now)
            and now - self._last_seen > self.cfg.lost_timeout_s
        ):
            self.robot.stop()
            self._go(State.SEARCH, now, "lost the object")
            return
        if self._orbit_left:
            self.robot.drive(self._orbit_step(now))
            return
        # Seen, too close to be seen, or out of sight for a moment (the edge of the image, a
        # blurred frame): keep going to where the odometry says it is. Standing still, as before,
        # could never bring it back into view.
        velocity, arrived = self._object_ctrl.step(self._track.x_m, self._track.y_m)
        self.robot.drive(velocity)
        if arrived:
            self._go(State.PICK, now, "at pre-grasp pose")
        elif now - self._entered > self.cfg.approach_timeout_s:
            self._go(State.SEARCH, now, "approach timeout")

    def _on_pick(self, scene: Scene, now: float) -> None:
        assert self._track is not None
        self.robot.stop()
        self._pick_attempts += 1
        if self.pick.run(self.robot, self._track):
            self.carrying = self._track.category
            self.stats.picked += 1
            self._failed_objects = 0
            self._go(State.FIND_STATION, now, f"holding {self._track.label}")
            return
        self.stats.failed_picks += 1
        if self._pick_attempts < self.cfg.max_pick_attempts:
            self._object_ctrl.reset()
            self._last_seen = now
            self._go(State.APPROACH, now, f"pick failed, retry {self._pick_attempts}")
            return
        if self._orbits < len(self.cfg.orbit_deg):
            side = float(self.cfg.orbit_deg[self._orbits])
            self._orbit_left = math.radians(side) - self._orbit_offset
            self._orbit_offset = math.radians(side)
            self._orbits += 1
            self._orbit_circling, self._pick_attempts = False, 0
            self._object_ctrl.reset()
            self._last_seen = now
            self._go(State.APPROACH, now, f"{self.cfg.max_pick_attempts} grasps failed: trying from {side:+.0f} deg round it")  # fmt: skip
            return
        self.stats.abandoned += 1
        self._failed_objects += 1
        if self._failed_objects >= self.cfg.max_failed_objects:
            self._go(State.FAILED, now, "too many objects could not be picked")
        else:
            self._go(State.BACK_OFF, now, "giving up on this object")

    def _on_find_station(self, scene: Scene, now: float) -> None:
        if self.carrying in scene.stations:
            self._station_ctrl.reset()
            self._last_seen = now
            self._go(State.GO_TO_STATION, now, f"{self.carrying.value} station in sight")
            return
        self.robot.drive(BaseVelocity(theta=self.cfg.search_speed))
        if (now - self._entered) * self.cfg.search_speed > self.cfg.search_turns * 2 * math.pi:
            self._go(State.FAILED, now, f"no {self.carrying.value} station found")

    def _on_go_to_station(self, scene: Scene, now: float) -> None:
        station = scene.stations.get(self.carrying)
        if station is None:
            self.robot.stop()
            if now - self._last_seen > self.cfg.lost_timeout_s:
                self._go(State.FIND_STATION, now, "lost the station")
            return
        self._last_seen = now
        velocity, arrived = self._station_ctrl.step(station.x_m, station.y_m)
        self.robot.drive(velocity)
        if arrived:
            self._drop_attempts = 0
            self._go(State.DROP, now, "in front of the station")
        elif now - self._entered > self.cfg.approach_timeout_s:
            self._go(State.FIND_STATION, now, "station approach timeout")

    def _on_drop(self, scene: Scene, now: float) -> None:
        self.robot.stop()
        self._drop_attempts += 1
        if self.drop.run(self.robot, self.carrying):
            self.stats.delivered += 1
            self.carrying = None
            self._go(State.BACK_OFF, now, "delivered")
        elif self._drop_attempts >= self.cfg.max_drop_attempts:
            self._go(State.FAILED, now, "drop failed")

    def _on_back_off(self, scene: Scene, now: float) -> None:
        if now - self._entered < self.cfg.back_off_s:
            self.robot.drive(BaseVelocity(x=-self.cfg.back_off_speed))
        else:
            self._go(State.SEARCH, now, "backed off")

    def _on_done(self, scene: Scene, now: float) -> None:
        self.robot.stop()

    _on_failed = _on_done

    # --------------------------------------------------------------- helpers

    def _go(self, state: State, now: float, reason: str) -> None:
        event = Event(now, self.state, state, reason)
        self.events.append(event)
        log.info("[%7.2fs] %s -> %s (%s)", now, self.state.value, state.value, reason)
        self.state, self._entered = state, now
        if state in (State.PICK, State.DROP, *TERMINAL):
            self.robot.stop()
        if self.on_event:
            self.on_event(event)

    def _predict_track(self, velocity: BaseVelocity, now: float) -> None:
        """Move the tracked point the opposite way the base moved since the last tick."""
        dt = 0.0 if self._prev_stamp is None else max(0.0, now - self._prev_stamp)
        if dt > MAX_GAP_S:  # a blocking skill just ended: the base did not move meanwhile
            dt = 0.0
        self._prev_stamp = now
        if self._track is None or dt == 0.0:
            return
        x, y = self._track.x_m - velocity.x * dt, self._track.y_m - velocity.y * dt
        c, s = math.cos(-velocity.theta * dt), math.sin(-velocity.theta * dt)
        self._track = replace(self._track, x_m=c * x - s * y, y_m=s * x + c * y)

    def _in_blind_zone(self, now: float) -> bool:
        assert self._track is not None
        close = (
            0.0 < self._track.x_m < self.cfg.blind_below_x_m
            and abs(self._track.y_m) < self.cfg.blind_below_x_m
        )
        return close and now - self._last_seen < self.cfg.blind_timeout_s

    def _candidates(self, scene: Scene) -> list[Target]:
        def near_station(t: Target) -> bool:
            return any(
                math.hypot(t.x_m - s.x_m, t.y_m - s.y_m) < self.cfg.station_exclusion_m
                for s in scene.stations.values()
            )

        return [t for t in scene.targets if t.category is not Category.UNKNOWN and not near_station(t)]

    def _start_approach(self, scene: Scene, now: float) -> bool:
        target = min(self._candidates(scene), key=lambda t: t.distance_m, default=None)
        if target is None:
            return False
        self._track, self._last_seen, self._pick_attempts = target, now, 0
        self._reset_orbit()
        self._object_ctrl.reset()
        self._go(State.APPROACH, now, f"found {target.label} at {target.distance_m:.2f} m")
        return True

    def _reset_orbit(self) -> None:
        self._orbits = 0  # sides tried after the first one, for the current object
        self._orbit_offset = 0.0  # how far round the object the current side is (rad)
        self._orbit_left = 0.0  # still to go round it (rad, the base's turn); 0 = not going round
        self._orbit_circling = False  # backed away already: going round
        self._orbit_yaw = 0.0

    def _orbit_step(self, now: float) -> BaseVelocity:
        """One tick of going round the object, keeping it straight ahead: back away until it is
        `orbit_radius_m` off, then slide sideways while turning. The base turns by as much as it
        goes round, so going round by an angle is turning by it. Then the approach takes over."""
        track, cfg = self._track, self.cfg
        assert track is not None
        distance = math.hypot(track.x_m, track.y_m)
        too_long = now - self._entered > cfg.approach_timeout_s / 2
        if not self._orbit_circling:
            if distance < cfg.orbit_radius_m and not too_long:
                return BaseVelocity(x=-cfg.back_off_speed)
            self._orbit_circling, self._orbit_yaw = True, self.odometry.yaw
        left = self._orbit_left - math.remainder(self.odometry.yaw - self._orbit_yaw, math.tau)
        self._orbit_yaw = self.odometry.yaw
        if left * self._orbit_left <= 0.0 or abs(left) < math.radians(1.0) or too_long:
            self._orbit_left, self._orbit_circling = 0.0, False
            self._object_ctrl.reset()
            self._last_seen = now
            return BaseVelocity()
        self._orbit_left = left
        # Turning at `turn` with the object at (x, y), it stays put if the base moves by
        # (turn * y, -turn * x). Plus: keep it centred, and at the radius.
        turn = math.copysign(cfg.orbit_speed, left) + 1.0 * math.atan2(track.y_m, track.x_m)
        return BaseVelocity(
            x=turn * track.y_m + 0.8 * (distance - cfg.orbit_radius_m),
            y=-turn * track.x_m,
            theta=turn,
        )

    def _match_track(self, scene: Scene) -> Target | None:
        """The sighting that is most likely the object we were already approaching."""
        assert self._track is not None
        track = self._track
        # Matched by position only: the category may change as we get close enough to classify.
        best = min(
            self._candidates(scene),
            key=lambda t: math.hypot(t.x_m - track.x_m, t.y_m - track.y_m),
            default=None,
        )
        if best is None or math.hypot(best.x_m - track.x_m, best.y_m - track.y_m) > self.cfg.track_gate_m:
            return None
        return best
