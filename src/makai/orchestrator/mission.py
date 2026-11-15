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
    # Closer than this the object starts leaving the image and is easily taken for something
    # else: what it is seen as there counts only if it was never seen farther (15 Nov).
    classify_near_m: float = 0.55
    approach_timeout_s: float = 40.0
    track_gate_m: float = 0.30  # max jump between two sightings of the same object
    station_exclusion_m: float = 0.30  # ignore objects this close to a station (already delivered)
    max_pick_attempts: int = 3  # per object, from each side tried
    # After a missed grasp, back away to `orbit_radius_m` before trying again: the camera sees
    # the object again, where the grasp may have pushed it (it is out of view at the grasp pose).
    retry_from_afar: bool = True
    # After a grasp the gripper says held: back away to `orbit_radius_m` and look where the
    # object lay. Seen there in `verify_frames` images: missed. Not seen for `verify_look_s`: held.
    verify_pick: bool = True
    verify_look_s: float = 1.0
    verify_frames: int = 3
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
        # What the tracked object was seen as, summed confidence: from afar, and up close.
        self._votes: dict[Category, float] = {}
        self._votes_near: dict[Category, float] = {}
        self._verifying = False  # backed away after a grasp, looking whether the object is still there
        self._verify_seen = 0
        self._verify_since: float | None = None
        self._reset_orbit()

    # ------------------------------------------------------------------ loop

    def step(self) -> State:
        """One control tick: observe, perceive, act."""
        obs = self.robot.get_observation()
        self.scene = self.perception.perceive(obs)
        now = self.now = obs.stamp
        gap = 0.0 if self._prev_stamp is None else now - self._prev_stamp
        self.odometry.update(obs.base_velocity, now)
        self._predict_track(obs.base_velocity, now)
        if gap > MAX_GAP_S and self._entered is not None:
            # A blocking skill (a pick, 10 to 20 s; a drop) just ended. That time was not spent
            # looking for anything: without this, a missed pick read as "lost the object" (15 Nov).
            self._entered += gap
            self._last_seen += gap
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
        if self._verifying:
            self._verify_grasp(scene, now)
            return
        match = self._match_track(scene)
        if match is not None:
            if match.confidence > 0.0:
                votes = self._votes_near if match.distance_m < self.cfg.classify_near_m else self._votes
                votes[match.category] = votes.get(match.category, 0.0) + match.confidence
            if self._votes or self._votes_near:
                # What it is: what it was seen as most, all along the approach, not in the last
                # image. Up close the object leaves the image and a sock was taken for a can (15
                # Nov): what is seen that close counts only if it was never seen farther. A guess
                # from far away (no confidence) does not vote.
                votes = self._votes or self._votes_near
                kind = max(votes, key=votes.__getitem__)
                if match.category is not kind:
                    match = replace(match, category=kind, label=kind.value)
                match = replace(match, confidence=max(match.confidence, self._track.confidence))
            self._track, self._last_seen = match, now
        elif (
            not self._orbit_active  # backing away, going round it: followed on odometry, it shows again
            and not self._in_blind_zone(now)
            and now - self._last_seen > self.cfg.lost_timeout_s
        ):
            self.robot.stop()
            self._go(State.SEARCH, now, "lost the object")
            return
        if self._orbit_active:
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
        if not self.pick.run(self.robot, self._track):
            self._missed(now)
        elif self.cfg.verify_pick:
            # The gripper says held. A sock pinched by the tip, a few threads of carpet, read the
            # same (15 Nov). Check with the camera: back away and look at the floor where it lay.
            self._verifying, self._verify_seen, self._verify_since = True, 0, None
            self._orbit_active, self._orbit_left, self._orbit_circling = True, 0.0, False
            self._object_ctrl.reset()
            self._last_seen = now
            self._go(
                State.APPROACH, now, f"checking the grasp: is the {self._track.label} still on the floor?"
            )
        else:
            self._picked(now)

    def _verify_grasp(self, scene: Scene, now: float) -> None:
        """Backed away from where the object lay: is it still there? Seen there in a few images:
        the grasp missed. Not seen for `verify_look_s`: it is held."""
        if self._orbit_active:
            self.robot.drive(self._orbit_step(now))
            return
        self.robot.stop()
        self._verify_since = now if self._verify_since is None else self._verify_since
        if self._match_track(scene) is not None:
            self._verify_seen += 1
        if self._verify_seen >= self.cfg.verify_frames:
            self._verifying = False
            self._missed(now, "still on the floor: pick failed")
        elif now - self._verify_since >= self.cfg.verify_look_s:
            self._verifying = False
            self._picked(now)

    def _picked(self, now: float) -> None:
        assert self._track is not None
        self.carrying = self._track.category
        self.stats.picked += 1
        self._failed_objects = 0
        self._go(State.FIND_STATION, now, f"holding {self._track.label}")

    def _missed(self, now: float, why: str = "pick failed") -> None:
        self.stats.failed_picks += 1
        if self._pick_attempts < self.cfg.max_pick_attempts:
            self._object_ctrl.reset()
            self._last_seen = now
            if self.cfg.retry_from_afar:  # back away until it is in view again: the grasp may have pushed it
                self._orbit_active, self._orbit_left, self._orbit_circling = True, 0.0, False
            self._go(State.APPROACH, now, f"{why}, retry {self._pick_attempts}")
            return
        if self._orbits < len(self.cfg.orbit_deg):
            side = float(self.cfg.orbit_deg[self._orbits])
            self._orbit_active, self._orbit_left = True, math.radians(side) - self._orbit_offset
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
        self._verifying = False
        self._votes, self._votes_near = {}, {}
        if target.confidence > 0.0:
            near = target.distance_m < self.cfg.classify_near_m
            (self._votes_near if near else self._votes)[target.category] = target.confidence
        self._reset_orbit()
        self._object_ctrl.reset()
        self._go(State.APPROACH, now, f"found {target.label} at {target.distance_m:.2f} m")
        return True

    def _reset_orbit(self) -> None:
        self._orbit_active = False  # backing away from the object, then going round it if `_orbit_left`
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
            # Done (or only backing away was asked): the approach takes over, on what it sees.
            self._orbit_active, self._orbit_left, self._orbit_circling = False, 0.0, False
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
