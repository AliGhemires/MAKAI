"""The mission that covers a zone and tidies what it finds: a robot vacuum, or a patrol.

    SWEEP -> (object in sight) -> APPROACH -> PICK -> DOCK -> GO_TO_STATION -> DROP -> BACK_OFF
          -> RESUME (back to where the route was left) -> SWEEP ... -> RETURN_HOME -> DONE

The robot starts at the origin of the map: in front of the bin, back to it, facing the zone.
It follows a route over the zone (SWEEP) and leaves it for the objects it finds (every other
state). Two uses, which differ only in the route and in what makes the robot leave it:

Vacuum and collect (`pattern: rows`), a hotel room. The robot is there to pass over the whole
floor. It never turns: it keeps facing the zone, square to the wall behind it, and slides
along rows (`navigation.coverage.row_waypoints`). It only picks up what lies on its way: the
objects closer than `pickup_range_m`, in the strip of floor it is about to reach.

Scan and collect (`pattern: scan`), a street. The robot is there to find things. It drives
down wide lanes (`scan_waypoints`) while its heading swings left and right, so the camera
looks over a wide strip, and it goes to whatever it spots, as far as the camera sees.

In both, once an object is in sight the robot places itself in front of it with the camera
(the approach of the base mission, free to turn), runs the pick policy, drives back to the
dock of the right station on odometry, finishes on the station's marker when it sees it, and
drops. It then goes back to the exact spot it left and carries on. Every visit to a station
also puts the odometry right: the marker's position is known, so the drift accumulated on
the way is erased.

Everything the base mission does to approach and pick is reused unchanged; this class replaces
only how the robot searches and how it goes to the stations.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace

from makai.contracts import (
    BaseVelocity,
    Category,
    DropSkill,
    Perception,
    PickSkill,
    Robot,
    Scene,
    StationSighting,
    Target,
)
from makai.navigation.approach import ApproachController
from makai.navigation.coverage import Room, row_waypoints, scan_waypoints, snake_waypoints
from makai.navigation.mapping import MapObject, RoomMap
from makai.orchestrator.mission import Event, Mission, MissionConfig, State


@dataclass(frozen=True)
class Station:
    """A bin or a basket, in the map frame, and where the robot stops in front of it."""

    x: float
    y: float
    dock_x: float = 0.0
    dock_y: float = 0.0

    @property
    def heading(self) -> float:
        """The way the robot faces when it stands at the dock, looking at the station."""
        return math.atan2(self.y - self.dock_y, self.x - self.dock_x)


@dataclass(frozen=True)
class SweepConfig:
    room: Room = field(default_factory=Room)
    # "rows": vacuum and collect. The robot never turns while it sweeps: it faces the zone,
    # square to the wall behind it, and slides sideways along rows.
    # "scan": scan and collect. It drives down wide lanes while its heading swings left and
    # right, and goes to whatever it spots.
    # "lanes": the earlier vacuum path. The robot turns to follow lanes that run into the zone.
    pattern: str = "rows"
    lane_spacing_m: float = 0.5  # between two rows (or two lanes)
    # Vacuum: the robot only leaves its route for an object this close, the ones on its way.
    # 0 = for anything the camera sees.
    pickup_range_m: float = 1.0
    scan_swath_m: float = 1.6  # scan: width of the strip of floor looked at from one lane
    scan_speed: float = 0.08  # scan: m/s along the lanes, slow enough to look both ways on the way
    scan_pan_deg: float = 60.0  # scan: the heading swings this far to each side of the way it drives
    scan_period_s: float = 10.0  # scan: time of one swing, left and right
    # The bin stands just behind the start pose: the origin is its dock. An object whose
    # category has no station of its own goes to the first one listed.
    stations: Mapping[Category, Station] = field(
        default_factory=lambda: {Category.TRASH: Station(-0.35, 0.0)}
    )
    sweep_speed: float = 0.15  # m/s along the lanes
    waypoint_tol_m: float = 0.04
    dock_tol_m: float = 0.02  # in front of a station the robot must stand more exactly
    heading_tol_deg: float = 3.0
    min_turn: float = 0.25  # rad/s, below this the base does not turn (stiction)
    marker_wait_s: float = 1.0  # at the dock, how long to look for the station's marker in each direction
    # Drift can leave the marker out of the camera's view: look this far to each side, in degrees.
    marker_scan_deg: tuple[float, ...] = (35.0, -35.0, 70.0, -70.0, 105.0, -105.0, 140.0, -140.0, 180.0)
    # Drive back to the first station to check the position on its marker after this many
    # metres without seeing one. 0 = only when delivering. Raise it on a floor that grips well.
    recheck_after_m: float = 0.0
    max_dock_tries: int = 3  # markers lost this many times in one delivery: drop on odometry
    travel_timeout_s: float = 120.0  # for one leg driven on odometry
    room_slack_m: float = 0.10  # an object this far outside the walls is still accepted
    abandon_radius_m: float = 0.30  # do not go back to an object that was given up
    max_yaw_fix_deg: float = 75.0  # a larger heading correction is a bad marker reading
    # Whenever a station's marker is in view, the camera corrects the odometry, a little at
    # every image: the heading from the direction the marker is seen in, the position from its
    # distance. With the bin across the zone, facing the robot, this goes on all along the sweep.
    marker_fix_range_m: float = 2.5  # markers further than this are not trusted for it
    marker_fix_gain: float = 0.15  # share of the gap closed at each image
    marker_fix_gate_m: float = 0.6  # a larger gap in distance is a bad reading, or a marker moved
    marker_fix_gate_deg: float = 35.0  # the same for the heading
    # Closer than this, a few centimetres of sideways error look like degrees of heading: the
    # heading is then left to the reading made at the dock, where the marker's own tilt shows.
    marker_fix_heading_from_m: float = 0.8
    camera_range_m: float = 1.5  # how far the camera is trusted, for the coverage map
    camera_hfov_deg: float = 55.0  # its horizontal field of view, for the coverage map


# The states in which the robot has left its route and will come back to it.
AWAY = (State.APPROACH, State.PICK, State.DOCK, State.GO_TO_STATION, State.DROP, State.BACK_OFF, State.RESUME)

# In vacuum mode the robot faces the room, as at the start: square to the wall behind it.
SWEEP_HEADING = 0.0


# The two uses of the mission, as the console and `makai-mission --use` name them.
USES = ("vacuum", "scan")


def sweep_waypoints(cfg: SweepConfig) -> list[tuple[float, float]]:
    """The route of the sweep, for the pattern chosen in the config."""
    if cfg.pattern == "rows":
        return row_waypoints(cfg.room, cfg.lane_spacing_m)
    if cfg.pattern == "scan":
        return scan_waypoints(cfg.room, cfg.scan_swath_m)
    if cfg.pattern == "lanes":
        return snake_waypoints(cfg.room, cfg.lane_spacing_m)
    raise ValueError(f"navigation.sweep.pattern must be 'rows', 'scan' or 'lanes', not {cfg.pattern!r}")


def for_use(cfg: SweepConfig, use: str) -> SweepConfig:
    """The config of one use. "vacuum" keeps the vacuum path of the config (rows, or lanes)."""
    if use == "scan":
        return replace(cfg, pattern="scan")
    if use == "vacuum":
        return cfg if cfg.pattern in ("rows", "lanes") else replace(cfg, pattern="rows")
    raise ValueError(f"The use must be one of {USES}, not {use!r}")


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


class SweepMission(Mission):
    def __init__(
        self,
        robot: Robot,
        perception: Perception,
        pick: PickSkill,
        drop: DropSkill,
        cfg: MissionConfig | None = None,
        sweep: SweepConfig | None = None,
        on_event: Callable[[Event], None] | None = None,
    ):
        super().__init__(robot, perception, pick, drop, cfg, on_event)
        self.sweep = sweep or SweepConfig()
        self.state = State.SWEEP
        self.waypoints = sweep_waypoints(self.sweep)
        self.map = RoomMap(
            self.sweep.room, hfov_deg=self.sweep.camera_hfov_deg, max_range_m=self.sweep.camera_range_m
        )
        self.last_correction_m: float | None = None  # how far the last visit to a station moved the pose
        self._waypoint = 0
        self._nav = ApproachController(
            replace(
                self.cfg.approach,
                goal_x_m=0.0,
                goal_y_m=0.0,
                tol_x_m=self.sweep.waypoint_tol_m,
                tol_y_m=self.sweep.waypoint_tol_m,
                settle_ticks=1,
                max_lin=self.sweep.sweep_speed,
            )
        )
        self._dock_nav = ApproachController(
            replace(self._nav.cfg, tol_x_m=self.sweep.dock_tol_m, tol_y_m=self.sweep.dock_tol_m)
        )
        # Following the route: the same gains, but translating only, never turning towards the point.
        speed = self.sweep.scan_speed if self.sweep.pattern == "scan" else self.sweep.sweep_speed
        self._slide = ApproachController(replace(self._nav.cfg, near_radius_m=math.inf, max_lin=speed))
        self._slide_exact = ApproachController(
            replace(self._slide.cfg, tol_x_m=self.sweep.dock_tol_m, tol_y_m=self.sweep.dock_tol_m)
        )
        if self.sweep.pattern == "rows":
            # Vacuum: the base never turns towards what it goes to, object or marker. It slides.
            self._object_ctrl = ApproachController(replace(self._object_ctrl.cfg, near_radius_m=math.inf))
            self._station_ctrl = ApproachController(replace(self._station_ctrl.cfg, near_radius_m=math.inf))
        self.locked_at: float | None = None  # when a marker last told the robot where it is
        self._nav_target: tuple[float, float, object] | None = None
        self._course = SWEEP_HEADING  # scan: the way the current leg of the route goes
        self._leg_started = 0.0  # scan: when the robot set off on this leg (or came back to it)
        self._anchored = False  # this delivery's position was already checked on the marker
        self._since_anchor_m = 0.0  # distance driven since a marker last put the position right
        self._last_xy = (0.0, 0.0)
        self._resume: tuple[float, float, float] | None = None  # pose to come back to
        self._arrived = False  # the position part of the current leg is done; the heading is next
        self._faced_at: float | None = None
        self._station_key: Category = next(iter(self.sweep.stations))
        self._home_key: Category = next(iter(self.sweep.stations))  # the mission ends at its dock
        self._home_step = 0
        self._scan = 0  # which direction of the marker search is being looked at
        self._dock_tries = 0
        self._object: MapObject | None = None

    # ------------------------------------------------------------------ loop
    def step(self) -> State:
        state = super().step()
        self._fix_on_markers(self.scene)
        pose = self.odometry
        self._since_anchor_m += math.dist(self._last_xy, (pose.x, pose.y))
        self._last_xy = (pose.x, pose.y)
        self.map.see_from(pose.x, pose.y, pose.yaw)
        for target in self._candidates(self.scene):
            self.map.note(target.label, target.category.value, *self._to_map(target.x_m, target.y_m))
        return state

    # ---------------------------------------------------------------- states
    def _on_sweep(self, scene: Scene, now: float) -> None:
        if self._leave_route_for_object(scene, now):
            return
        if self._waypoint >= len(self.waypoints):
            self._go(State.RETURN_HOME, now, "room swept")
        elif 0.0 < self.sweep.recheck_after_m < self._since_anchor_m:
            self._resume = (self.odometry.x, self.odometry.y, self.odometry.yaw)
            self._station_key = self._home_key
            self._dock_tries, self._anchored = 0, False
            self._go(State.DOCK, now, f"{self._since_anchor_m:.1f} m without a marker: checking the position")
        elif self._follow(*self.waypoints[self._waypoint]):
            self._waypoint += 1

    def _on_resume(self, scene: Scene, now: float) -> None:
        if self._start_approach(scene, now):  # another object on the way back: same resume pose
            return
        x, y, yaw = self._resume or (self.odometry.x, self.odometry.y, self.odometry.yaw)
        if self.sweep.pattern == "rows":
            yaw = SWEEP_HEADING  # back to vacuuming: square to the wall, whatever it was when it left
        elif self.sweep.pattern == "scan":
            yaw = self._course  # back to scanning: facing the way the route goes
        if not self._arrived:
            late = now - self._entered > self.sweep.travel_timeout_s
            self._arrived = self._travel(x, y, heading=yaw) or late
        elif self._face(yaw):
            self._go(State.SWEEP, now, "back on the route")

    def _on_return_home(self, scene: Scene, now: float) -> None:
        """Back to the origin on odometry, then onto the bin's marker to erase the drift of the
        last stretch, and finally facing the room again, as at the start."""
        if self._home_step == 0 and self._leave_route_for_object(scene, now):
            return
        station = self.sweep.stations[self._home_key]
        if self.starts_away_from_dock:
            # The bin stands across the zone: home is the start pose, at the near edge. The
            # marker, in view on the way back, keeps the position right.
            late = now - self._entered > self.sweep.travel_timeout_s
            if self._home_step == 0 and (self._travel(0.0, 0.0, exact=True) or late):
                self._home_step = 1
            elif self._home_step == 1 and self._face(SWEEP_HEADING):
                self._go(State.DONE, now, "zone swept, back at the start")
            return
        if self._home_step in (
            0,
            3,
        ):  # 0: to the dock on odometry; 3: again, once the marker has put it right
            late = now - self._entered > self.sweep.travel_timeout_s
            if self._travel(station.dock_x, station.dock_y, exact=True, heading=station.heading) or late:
                self._home_step, self._faced_at, self._scan = self._home_step + 1, None, 0
        elif self._home_step == 1:  # face the station and look for its marker
            found = self._find_marker(self._home_key, scene, now, station.heading)
            if found:
                self._station_ctrl.reset()
                self._home_step = 2
            elif found is False:
                self._home_step = 4  # no marker: the odometry will have to do
        elif self._home_step == 2:  # the last centimetres on the marker
            sighting = scene.stations.get(self._home_key)
            if sighting is None:
                self.robot.stop()
                self._home_step = 4
                return
            velocity, arrived = self._station_ctrl.step(sighting.x_m, sighting.y_m)
            self.robot.drive(velocity)
            if arrived:
                self._anchor(sighting, self._home_key)
                self._home_step = 3
        elif self._face(station.heading + math.pi):
            self._go(State.DONE, now, "room swept, back in front of the bin")

    def _on_dock(self, scene: Scene, now: float) -> None:
        """Go to the station. As soon as the camera sees it, steer on what the camera sees.
        Until then: drive to its dock on odometry, face the station, look for its marker."""
        station = self.sweep.stations[self._station_key]
        if not self._anchored and self._station_key in scene.stations:
            # In sight, from wherever the robot is: no need to trust the odometry up to the dock.
            self._station_ctrl.reset()
            self._last_seen = now
            self._go(State.GO_TO_STATION, now, "station in sight")
            return
        if not self._arrived:
            self._arrived = self._travel(station.dock_x, station.dock_y, exact=True, heading=station.heading)
            if not self._arrived and now - self._entered > self.sweep.travel_timeout_s:
                self._go(State.FAILED, now, "could not reach the station")
            return
        if self.carrying is None:  # a visit only to check the position: no need to stand square
            found = self._anchored or self._find_marker(self._station_key, scene, now, station.heading)
            if found and not self._anchored:
                self._station_ctrl.reset()
                self._last_seen = now
                self._go(State.GO_TO_STATION, now, "station marker in sight")
            elif found is not None:
                self._since_anchor_m = 0.0  # checked, or no marker to check on: do not come straight back
                self._go(State.RESUME, now, "position checked" if self._anchored else "no marker in sight")
            return
        if self._anchored:  # the marker already put the position right: stand square and drop
            if self._face(station.heading):
                self._drop_attempts = 0
                self._go(State.DROP, now, "in front of the station")
            return
        found = (
            False
            if self._dock_tries > self.sweep.max_dock_tries
            else self._find_marker(self._station_key, scene, now, station.heading)
        )
        if found:
            self._station_ctrl.reset()
            self._last_seen = now
            self._go(State.GO_TO_STATION, now, "station marker in sight")
        elif found is False and self._face(station.heading):
            self._drop_attempts = 0
            self._go(State.DROP, now, "no marker in sight: dropping on odometry")

    def _on_go_to_station(self, scene: Scene, now: float) -> None:
        """The last centimetres, on the station's marker. Arriving also puts the odometry right."""
        sighting = scene.stations.get(self._station_key)
        if sighting is None:
            self.robot.stop()
            if now - self._last_seen > self.cfg.lost_timeout_s:
                self._go(State.DOCK, now, "lost the marker")
            return
        self._last_seen = now
        velocity, arrived = self._station_ctrl.step(sighting.x_m, sighting.y_m)
        self.robot.drive(velocity)
        if arrived:
            self._anchor(sighting, self._station_key)
            self._anchored = True
            self._go(State.DOCK, now, "position checked on the marker")
        elif now - self._entered > self.cfg.approach_timeout_s:
            self._drop_attempts = 0
            late = "station approach timeout"
            self._go(
                State.DROP if self.carrying else State.RESUME,
                now,
                f"{late}: dropping here" if self.carrying else late,
            )

    def _on_pick(self, scene: Scene, now: float) -> None:
        abandoned = self.stats.abandoned
        super()._on_pick(scene, now)
        if self._object is not None:
            if self.state is State.DOCK:
                self._object.status = "picked"
            elif self.stats.abandoned > abandoned:
                self._object.status = "abandoned"

    def _on_drop(self, scene: Scene, now: float) -> None:
        delivered = self.stats.delivered
        super()._on_drop(scene, now)
        if self.stats.delivered > delivered and self._object is not None:
            station = self.sweep.stations[self._station_key]
            self._object.status, self._object.x, self._object.y = "delivered", station.x, station.y
            self._object = None

    # --------------------------------------------------------------- helpers
    def _go(self, state: State, now: float, reason: str) -> None:
        """The base mission searches by turning on the spot and finds stations by looking around.
        Here, "search again" means going back to the route, and "find the station" means docking."""
        if state is State.SEARCH:
            state = State.RESUME
            if self._object is not None and self._object.status == "approaching":
                self._object.status = "seen"
        elif state is State.FIND_STATION:
            state = State.DOCK
            wanted = (
                self.carrying if self.carrying in self.sweep.stations else next(iter(self.sweep.stations))
            )
            self._station_key = wanted
        if state in (State.RESUME, State.DOCK, State.RETURN_HOME):
            self._arrived, self._faced_at, self._home_step, self._scan = False, None, 0, 0
        if state is State.DOCK:
            if self.state is State.PICK:  # a new delivery
                self._dock_tries, self._anchored = 0, False
            self._dock_tries += 1
        super()._go(state, now, reason)

    def _leave_route_for_object(self, scene: Scene, now: float) -> bool:
        pose = (self.odometry.x, self.odometry.y, self.odometry.yaw)
        if not self._start_approach(scene, now):
            return False
        self._resume = pose
        return True

    def _start_approach(self, scene: Scene, now: float) -> bool:
        reach = self.sweep.pickup_range_m if self.sweep.pattern != "scan" else 0.0
        if reach > 0.0 and all(target.distance_m > reach for target in self._candidates(scene)):
            return False  # vacuuming: what is further away is not on its way yet
        if not super()._start_approach(scene, now):
            return False
        track = self._track
        self._object = self.map.note(
            track.label, track.category.value, *self._to_map(track.x_m, track.y_m), status="approaching"
        )
        return True

    def _candidates(self, scene: Scene) -> list[Target]:
        """Objects worth going to: inside the room, not in a station, not given up before."""
        keep = []
        for target in scene.targets:
            if target.category is Category.UNKNOWN:
                continue
            x, y = self._to_map(target.x_m, target.y_m)
            in_station = any(
                math.hypot(x - s.x, y - s.y) < self.cfg.station_exclusion_m
                for s in self.sweep.stations.values()
            )
            given_up = self.map.nearest(x, y, self.sweep.abandon_radius_m, ("abandoned",)) is not None
            if self.sweep.room.contains(x, y, self.sweep.room_slack_m) and not in_station and not given_up:
                keep.append(target)
        return keep

    def _to_map(self, x_base: float, y_base: float) -> tuple[float, float]:
        pose = self.odometry
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        return pose.x + c * x_base - s * y_base, pose.y + s * x_base + c * y_base

    def _to_base(self, x: float, y: float) -> tuple[float, float]:
        pose = self.odometry
        dx, dy = x - pose.x, y - pose.y
        c, s = math.cos(-pose.yaw), math.sin(-pose.yaw)
        return c * dx - s * dy, s * dx + c * dy

    def _drive_to(self, x: float, y: float, exact: bool = False) -> bool:
        """One tick towards a point of the map, on odometry. True once there (and stopped)."""
        nav = self._dock_nav if exact else self._nav
        if self._nav_target != (x, y, exact):
            self._nav_target = (x, y, exact)
            nav.reset()
        velocity, arrived = nav.step(*self._to_base(x, y))
        self.robot.drive(velocity)
        return arrived

    def _follow(self, x: float, y: float) -> bool:
        """One tick along the route of the sweep. True once at this corner of the route."""
        if self.sweep.pattern == "rows":
            return self._slide_to(x, y)
        if self.sweep.pattern == "scan":
            return self._scan_to(x, y)
        return self._drive_to(x, y)

    def _scan_to(self, x: float, y: float) -> bool:
        """One tick towards a point of the map while looking left and right: the base translates
        along the leg, and its heading swings around the way it goes. True once there.

        Before setting off on a leg, and each time it comes back to it, the robot looks left and
        right once from where it stands. Each swing to the left is undone by a swing to the
        right, so what the wheels slip while turning cancels out instead of adding up."""
        pose = self.odometry
        period = self.sweep.scan_period_s
        if self._nav_target != (x, y, "scan"):
            self._nav_target = (x, y, "scan")
            self._slide.reset()
            if math.hypot(x - pose.x, y - pose.y) > self.sweep.waypoint_tol_m:
                self._course = math.atan2(y - pose.y, x - pose.x)
                self._leg_started = self.now
        pan = math.radians(self.sweep.scan_pan_deg)
        swing = pan * math.sin(2 * math.pi * (self.now - self._leg_started) / period)
        limit = self.cfg.approach.max_ang
        turn = max(-limit, min(limit, self.cfg.approach.k_ang * _wrap(self._course + swing - pose.yaw)))
        velocity, arrived = self._slide.step(*self._to_base(x, y))
        if arrived:
            self.robot.stop()
            return True
        off_course = abs(_wrap(self._course - pose.yaw)) > pan + math.radians(25.0)
        if off_course or self.now - self._leg_started < period:
            # A new leg: face its way, then look left and right once before moving.
            if off_course:
                self._leg_started = self.now
            self.robot.drive(BaseVelocity(theta=turn))
            return False
        self.robot.drive(replace(velocity, theta=turn))
        return False

    def _slide_to(self, x: float, y: float, exact: bool = False, heading: float = SWEEP_HEADING) -> bool:
        """One tick towards a point of the map without turning towards it: the base keeps
        `heading` (facing the zone, unless told otherwise) and only translates. True once there."""
        if abs(_wrap(heading - self.odometry.yaw)) > math.radians(self.sweep.heading_tol_deg):
            self._face(heading)  # not square (a marker just corrected the heading): square up first
            return False
        slide = self._slide_exact if exact else self._slide
        if self._nav_target != (x, y, "slide", exact):
            self._nav_target = (x, y, "slide", exact)
            slide.reset()
        velocity, arrived = slide.step(*self._to_base(x, y))
        self.robot.drive(velocity)
        return arrived

    def _travel(self, x: float, y: float, exact: bool = False, heading: float = SWEEP_HEADING) -> bool:
        """One tick towards a point off the route (a dock, the spot to resume from, the start).
        Vacuum: sliding, with the base kept at `heading`. Otherwise: facing the way it goes."""
        if self.sweep.pattern == "rows":
            return self._slide_to(x, y, exact, heading)
        return self._drive_to(x, y, exact)

    @property
    def starts_away_from_dock(self) -> bool:
        """The bin does not stand behind the start pose but somewhere else, as across the zone:
        the mission then ends back at the start pose, not at the bin's dock."""
        home = self.sweep.stations[self._home_key]
        return math.hypot(home.dock_x, home.dock_y) > 0.3

    def _fix_on_markers(self, scene: Scene) -> None:
        """A station's marker in view corrects the odometry, a little at every image.

        One marker gives two things well: the direction it is seen in, and its distance. What
        drifts most is the heading (it then drags the position along), so the direction corrects
        the heading, and the distance corrects the position along the line of sight. Doing it
        the other way round, the position from the direction, moved the robot sideways by as
        much as its heading was wrong: 60 cm at 2 m for 18 degrees.
        The marker's own tilt, which would give the heading directly, only shows up close: it is
        read when the robot arrives at the dock (`_anchor`).
        """
        if self.state in (State.PICK, State.DROP, State.DONE, State.FAILED):
            return
        pose, cfg = self.odometry, self.sweep
        for key, sighting in scene.stations.items():
            station = cfg.stations.get(key)
            if station is None or not 0.3 <= sighting.distance_m <= cfg.marker_fix_range_m:
                continue
            expected = math.atan2(station.y - pose.y, station.x - pose.x) - pose.yaw
            turn = _wrap(expected - math.atan2(sighting.y_m, sighting.x_m))
            if abs(turn) > math.radians(cfg.marker_fix_gate_deg):
                continue
            if sighting.distance_m >= cfg.marker_fix_heading_from_m:
                pose.yaw += cfg.marker_fix_gain * turn
            # Towards or away from the marker, by what its distance says.
            gap = math.hypot(station.x - pose.x, station.y - pose.y) - sighting.distance_m
            if abs(gap) <= cfg.marker_fix_gate_m:
                towards = math.atan2(station.y - pose.y, station.x - pose.x)
                pose.x += cfg.marker_fix_gain * gap * math.cos(towards)
                pose.y += cfg.marker_fix_gain * gap * math.sin(towards)
            self._last_xy = (pose.x, pose.y)
            self._since_anchor_m, self.locked_at = 0.0, self.now

    def _face(self, yaw: float) -> bool:
        """One tick of turning on the spot towards a heading of the map. True once aligned."""
        error = _wrap(yaw - self.odometry.yaw)
        if abs(error) <= math.radians(self.sweep.heading_tol_deg):
            self.robot.stop()
            return True
        limit = self.cfg.approach.max_ang
        turn = max(-limit, min(limit, self.cfg.approach.k_ang * error))
        if abs(turn) < self.sweep.min_turn:
            turn = math.copysign(self.sweep.min_turn, error)
        self.robot.drive(BaseVelocity(theta=turn))
        return False

    def _find_marker(self, key: Category, scene: Scene, now: float, heading: float) -> bool | None:
        """At a dock: face the station, then look to each side for its marker.

        True: the marker is in sight. False: looked everywhere, not there. None: still looking.
        """
        offsets = (0.0, *self.sweep.marker_scan_deg)
        if self._scan >= len(offsets):
            return False
        if not self._face(heading + math.radians(offsets[self._scan])):
            self._faced_at = None  # still turning: a marker caught at the edge of the image does not count
        elif key in scene.stations:
            return True
        elif self._faced_at is None:
            self._faced_at = now
        elif now - self._faced_at > self.sweep.marker_wait_s:
            self._scan, self._faced_at = self._scan + 1, None
        return None

    def _anchor(self, sighting: StationSighting, key: Category) -> None:
        """The station's place in the map is known: seeing it tells where the robot really is."""
        station = self.sweep.stations[key]
        pose = self.odometry
        if sighting.facing_rad is not None:
            # The marker faces the dock. Its direction seen from the robot gives the heading.
            yaw = _wrap(station.heading + math.pi - sighting.facing_rad)
            if abs(_wrap(yaw - pose.yaw)) <= math.radians(self.sweep.max_yaw_fix_deg):
                pose.yaw = yaw
        c, s = math.cos(pose.yaw), math.sin(pose.yaw)
        x = station.x - (c * sighting.x_m - s * sighting.y_m)
        y = station.y - (s * sighting.x_m + c * sighting.y_m)
        self.last_correction_m = math.hypot(x - pose.x, y - pose.y)
        pose.x, pose.y = x, y
        self._since_anchor_m, self._last_xy = 0.0, (x, y)

    # ------------------------------------------------------------------ reading
    @property
    def use(self) -> str:
        return "scan" if self.sweep.pattern == "scan" else "vacuum"

    def snapshot(self) -> dict:
        """Everything the interface shows, as plain data."""
        pose = self.odometry
        target = None
        if self._track is not None and self.state in (State.APPROACH, State.PICK):
            target = [round(v, 3) for v in self._to_map(self._track.x_m, self._track.y_m)]
        return {
            "state": self.state.value,
            # The use of this mission, and what the robot is doing: following its route (the
            # name of the use) or away from it for an object ("collect").
            "use": self.use,
            "mode": "collect" if self.state in AWAY else self.use,
            "pattern": self.sweep.pattern,
            "time_s": round(self.now, 1),
            "in_state_s": round(self.now - (self._entered or self.now), 1),
            "pose": {"x": round(pose.x, 3), "y": round(pose.y, 3), "yaw": round(pose.yaw, 3)},
            "carrying": self.carrying.value if self.carrying else None,
            "stats": vars(self.stats),
            "waypoints": self.waypoints,
            "waypoint": self._waypoint,
            "stations": {
                key.value: {"x": s.x, "y": s.y, "dock_x": s.dock_x, "dock_y": s.dock_y}
                for key, s in self.sweep.stations.items()
            },
            "target": target,
            "resume": [round(v, 3) for v in self._resume] if self._resume and self.state in AWAY else None,
            "anchor_m": None if self.last_correction_m is None else round(self.last_correction_m, 3),
            # A marker is in view and holds the position right now.
            "locked": self.locked_at is not None and self.now - self.locked_at < 0.5,
            "events": [
                {"t": round(e.stamp, 1), "from": e.previous.value, "to": e.state.value, "why": e.reason}
                for e in self.events[-16:]
            ],
            "map": self.map.snapshot(),
        }
