"""The sweeping mission, end to end on the simulated robot, and the pieces it is made of."""

import math

import pytest

from makai.contracts import Category, Scene, StationSighting
from makai.navigation.coverage import Room, path_length_m, row_waypoints, scan_waypoints, snake_waypoints
from makai.navigation.mapping import RoomMap
from makai.orchestrator.mission import MissionConfig, State
from makai.orchestrator.sweep import Station, SweepConfig, SweepMission, for_use
from makai.sim.world import (
    SimDrop,
    SimObject,
    SimPerception,
    SimPick,
    SimRobot,
    SimWorld,
    facing_world,
    sweep_world,
)

ROOM = Room(length_m=2.4, width_m=1.8)
TWO_STATIONS = {Category.TRASH: Station(-0.35, 0.0), Category.CLOTHING: Station(-0.35, 0.7, 0.0, 0.7)}


def build(
    world: SimWorld,
    stations=None,
    pick_success=1.0,
    slip=0.0,
    yaw_drift=0.0,
    room=ROOM,
    pattern="rows",
    **more,
) -> SweepMission:
    cfg = MissionConfig()
    return SweepMission(
        SimRobot(world, slip=slip, yaw_drift=yaw_drift),
        SimPerception(world, station_max_range_m=1.2, max_range_m=1.5),
        SimPick(world, goal_xy=(cfg.approach.goal_x_m, cfg.approach.goal_y_m), success_rate=pick_success),
        SimDrop(world),
        cfg,
        SweepConfig(room=room, stations=stations or TWO_STATIONS, pattern=pattern, **more),
    )


def test_snake_path_covers_the_width_and_stays_off_the_walls():
    points = snake_waypoints(ROOM, lane_spacing_m=0.5)
    assert points[0] == (0.3, -0.6)  # starts in the corner on the right, near the origin
    lanes = sorted({round(y, 3) for _, y in points})
    assert lanes == [-0.6, -0.2, 0.2, 0.6]
    assert all(b - a <= 0.5 + 1e-9 for a, b in zip(lanes, lanes[1:], strict=False))
    assert all(0.3 <= x <= 2.1 and abs(y) <= 0.6 for x, y in points)
    assert points[1] == (2.1, -0.6) and points[2] == (2.1, -0.2) and points[3] == (0.3, -0.2)  # a snake
    assert path_length_m(points) == pytest.approx(4 * 1.8 + 3 * 0.4)


def test_a_narrow_room_gets_one_lane():
    assert snake_waypoints(Room(length_m=2.0, width_m=0.6), 0.5) == [(0.3, 0.0), (1.7, 0.0)]


def test_rows_start_on_the_start_line_and_reach_the_far_end():
    points = row_waypoints(Room(length_m=2.0, width_m=1.6), row_spacing_m=0.5)
    assert points[:4] == [(0.0, -0.5), (0.0, 0.5), (0.5, 0.5), (0.5, -0.5)]  # across, one row forward, back
    rows = sorted({x for x, _ in points})
    assert rows == [0.0, 0.5, 1.0, 1.5]  # the last row looks at the half metre left before the far wall
    assert all(abs(y) == 0.5 for _, y in points)  # the robot's centre stays 30 cm from the side walls
    assert path_length_m(points) == pytest.approx(4 * 1.0 + 3 * 0.5)
    spread = sorted({x for x, _ in row_waypoints(ROOM, 0.5)})  # 2.4 m long: rows evenly spread
    assert spread[0] == 0.0 and spread[-1] == 1.9 and len(spread) == 5
    assert all(b - a <= 0.5 + 1e-9 for a, b in zip(spread, spread[1:], strict=False))


def test_rows_in_a_room_one_robot_wide_go_straight_ahead():
    assert row_waypoints(Room(length_m=2.0, width_m=0.6), 0.5) == [
        (0.0, 0.0),
        (0.5, 0.0),
        (1.0, 0.0),
        (1.5, 0.0),
    ]


def test_an_unknown_pattern_is_refused():
    with pytest.raises(ValueError, match="pattern"):
        build(sweep_world(), pattern="spiral")


def test_in_vacuum_mode_the_robot_never_turns():
    world = SimWorld(stations={Category.TRASH: (-0.35, 0.0)}, station_facing={Category.TRASH: 0.0})
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})  # nothing on the floor
    turned, sideways = 0.0, 0.0
    while mission.state is State.SWEEP and mission.now < 600:
        mission.step()
        if mission.state is State.SWEEP:
            turned += abs(mission.robot._vel.theta) * mission.robot.dt
            sideways += abs(mission.robot._vel.y) * mission.robot.dt
            assert abs(world.yaw) < 1e-6  # square to the wall behind it, all along
    assert mission.state is State.RETURN_HOME and turned == 0.0
    assert sideways == pytest.approx(0.6 + 5 * 1.2, abs=0.25)  # to the end of the start line, then five rows
    # Never seen while it sweeps: the 15 cm at the robot's feet and the two corners beside the start line.
    assert 0.88 < mission.map.coverage < 0.95


def test_comes_back_square_to_the_wall_after_each_object():
    world = sweep_world()
    mission = build(world, slip=0.04, yaw_drift=0.03)
    modes, squared = set(), []
    while mission.state not in (State.DONE, State.FAILED) and mission.now < 1500:
        before = mission.state
        mission.step()
        modes.add((mission.state, mission.snapshot()["mode"]) if mission.now % 5 < 0.04 else (None, None))
        if before is State.RESUME and mission.state is State.SWEEP:
            squared.append(abs(math.asin(math.sin(mission.odometry.yaw))))
    assert mission.state is State.DONE and len(world.delivered) == 4
    assert len(squared) == 4 and max(squared) <= math.radians(3.0) + 1e-9
    assert (State.SWEEP, "vacuum") in modes and (State.SWEEP, "collect") not in modes
    assert any(mode == "collect" for state, mode in modes if state in (State.APPROACH, State.DOCK))


def test_the_map_marks_what_the_camera_has_looked_at():
    room_map = RoomMap(ROOM, max_range_m=1.0)
    assert room_map.coverage == 0.0
    room_map.see_from(0.0, 0.0, 0.0)  # at the origin, looking into the room
    ahead = room_map.covered[len(room_map.ys) // 2]  # the row along y = 0
    assert ahead[10] and not ahead[-1]  # 0.5 m ahead is seen, 2.4 m ahead is out of range
    assert 0.0 < room_map.coverage < 0.3
    room_map.see_from(0.0, 0.0, math.pi)  # looking at the wall behind: nothing new
    assert room_map.covered[len(room_map.ys) // 2][10]


def test_the_map_keeps_one_entry_per_object():
    room_map = RoomMap(ROOM)
    first = room_map.note("can", "trash", 1.0, 0.2)
    again = room_map.note("can", "trash", 1.05, 0.22)  # the same can, seen a little better
    other = room_map.note("sock", "clothing", 1.8, -0.5)
    assert again is first and other is not first and len(room_map.objects) == 2
    assert (first.x, first.y) == (1.05, 0.22)


@pytest.mark.parametrize("pattern", ["rows", "lanes"])
def test_sweeps_the_room_and_tidies_everything(pattern):
    world = sweep_world()
    mission = build(world, pattern=pattern)
    assert mission.run(max_duration_s=1200) is State.DONE
    assert world.objects == [] and world.carrying is None
    assert sorted((o.label, s.value) for o, s in world.delivered) == [
        ("can", "trash"), ("can", "trash"), ("sock", "clothing"), ("sock", "clothing"),
    ]  # fmt: skip
    assert mission.map.coverage > 0.95
    assert (
        math.hypot(world.x, world.y) < 0.05 and abs(math.sin(world.yaw)) < 0.1
    )  # back at the origin, facing the room
    states = [e.state for e in mission.events]
    assert states.count(State.RESUME) == 4 and states[-2:] == [State.RETURN_HOME, State.DONE]
    assert [o.status for o in mission.map.objects] == ["delivered"] * 4


def test_goes_back_to_where_it_left_the_route():
    world = SimWorld(
        objects=[SimObject(1.5, -0.45, Category.TRASH, "can")], stations={Category.TRASH: (-0.35, 0.0)}
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    left_at = resumed_at = None
    while mission.state not in (State.DONE, State.FAILED) and mission.now < 600:
        before = mission.state
        mission.step()
        if before is State.SWEEP and mission.state is State.APPROACH:
            left_at = (world.x, world.y)
        if before is State.RESUME and mission.state is State.SWEEP:
            resumed_at = (world.x, world.y)
    assert mission.state is State.DONE and left_at is not None and resumed_at is not None
    assert math.dist(left_at, resumed_at) < 0.06


def test_the_marker_erases_the_drift_of_the_wheels():
    world = sweep_world()
    mission = build(world, slip=0.04, yaw_drift=0.03)
    assert mission.run(max_duration_s=1500) is State.DONE
    assert len(world.delivered) == 4
    assert (
        mission.last_correction_m is not None and mission.last_correction_m > 0.02
    )  # there was drift to erase
    assert math.hypot(world.x, world.y) < 0.04  # and the robot really is back at the origin
    assert abs(math.sin(world.yaw)) < 0.2  # the last half-turn, after the marker, is on odometry


def test_without_a_marker_it_still_drops_on_odometry():
    world = SimWorld(
        objects=[SimObject(1.2, 0.0, Category.TRASH, "can")], stations={Category.TRASH: (-0.35, 0.0)}
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    mission.perception.station_max_range = 0.0  # the marker is never seen
    assert mission.run(max_duration_s=600) is State.DONE
    assert len(world.delivered) == 1
    assert any("dropping on odometry" in e.reason for e in mission.events)


def test_one_bin_takes_everything():
    world = SimWorld(
        objects=[SimObject(1.2, 0.3, Category.CLOTHING, "sock"), SimObject(1.6, -0.3, Category.TRASH, "can")],
        stations={Category.TRASH: (-0.35, 0.0)},
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    assert mission.run(max_duration_s=900) is State.DONE
    assert len(world.delivered) == 2 and all(station is Category.TRASH for _, station in world.delivered)


def test_ignores_what_lies_outside_the_room():
    world = SimWorld(
        objects=[SimObject(1.2, 0.2, Category.TRASH, "can"), SimObject(3.2, 0.0, Category.TRASH, "far can")],
        stations={Category.TRASH: (-0.35, 0.0)},
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    assert mission.run(max_duration_s=900) is State.DONE
    assert [o.label for o in world.objects] == ["far can"] and len(world.delivered) == 1


def test_gives_up_on_an_object_and_does_not_come_back_to_it():
    world = SimWorld(
        objects=[
            SimObject(1.2, -0.5, Category.TRASH, "glued can"),
            SimObject(1.5, 0.5, Category.TRASH, "can"),
        ],
        stations={Category.TRASH: (-0.35, 0.0)},
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    grab = mission.pick.run
    mission.pick.run = lambda robot, target: target.label != "glued can" and grab(robot, target)
    assert mission.run(max_duration_s=1200) is State.DONE
    assert mission.stats.abandoned == 1 and mission.stats.failed_picks == 3 and mission.stats.delivered == 1
    assert [o.label for o in world.objects] == ["glued can"]
    assert sorted(o.status for o in mission.map.objects) == ["abandoned", "delivered"]


def test_the_snapshot_is_plain_data():
    import json

    world = sweep_world()
    mission = build(world)
    for _ in range(600):
        mission.step()
    shot = json.loads(json.dumps(mission.snapshot()))
    assert shot["state"] in {s.value for s in State}
    assert shot["map"]["room"]["length_m"] == 2.4 and len(shot["map"]["covered"]) == len(mission.map.ys)
    assert shot["waypoints"][0] == [0.0, -0.6] and "trash" in shot["stations"]
    assert shot["pattern"] == "rows" and shot["use"] == "vacuum" and shot["mode"] in ("vacuum", "collect")


def test_checks_its_position_on_the_marker_during_a_long_sweep():
    world = SimWorld(
        stations={Category.TRASH: (-0.35, 0.0)}, station_facing={Category.TRASH: 0.0}
    )  # nothing to pick
    cfg = MissionConfig()
    mission = SweepMission(
        SimRobot(world, slip=0.08, yaw_drift=0.06),
        SimPerception(world, station_max_range_m=1.2),
        SimPick(world),
        SimDrop(world),
        cfg,
        SweepConfig(room=ROOM, stations={Category.TRASH: Station(-0.35, 0.0)}, recheck_after_m=4.0),
    )
    assert mission.run(max_duration_s=2000) is State.DONE
    checks = [e for e in mission.events if "checking the position" in e.reason]
    assert len(checks) >= 2 and mission.stats.delivered == 0
    assert math.hypot(world.x, world.y) < 0.08  # heavy drift, and still back at the origin


def test_a_zone_off_centre_without_walls_is_swept_to_its_edges():
    # An imaginary rectangle traced with the robot: 2 m deep, from 0.3 m on its right to 0.9 m on its left.
    zone = Room(length_m=2.0, width_m=1.2, margin_m=0.0, y_offset_m=0.3)
    assert zone.y_range == pytest.approx((-0.3, 0.9))
    assert (
        zone.contains(1.0, 0.85) and not zone.contains(1.0, -0.45) and zone.contains(1.0, -0.35, slack_m=0.1)
    )
    points = row_waypoints(zone, 0.5)
    assert points[0] == (0.0, -0.3) and points[1] == (0.0, 0.9)  # the first row runs from edge to edge
    assert {round(y, 3) for _, y in snake_waypoints(zone, 0.5)} == {-0.3, 0.1, 0.5, 0.9}
    room_map = RoomMap(zone)
    assert room_map.ys[0] == pytest.approx(-0.275) and room_map.ys[-1] == pytest.approx(0.875)

    world = SimWorld(
        objects=[
            SimObject(1.2, 0.7, Category.TRASH, "can"),
            SimObject(1.5, -0.2, Category.CLOTHING, "sock"),
            SimObject(1.0, -0.8, Category.TRASH, "can outside"),
        ],
        stations={Category.TRASH: (-0.35, 0.0)},
        station_facing={Category.TRASH: 0.0},
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)}, room=zone)
    assert mission.run(max_duration_s=900) is State.DONE
    assert [o.label for o in world.objects] == ["can outside"] and len(world.delivered) == 2
    assert mission.map.coverage > 0.9  # without a margin only the 15 cm at the robot's feet stay unseen


# ---------------------------------------------------------------- the two uses
def test_the_vacuum_only_picks_up_what_lies_on_its_way():
    world = SimWorld(
        objects=[SimObject(1.4, 0.0, Category.TRASH, "can")], stations={Category.TRASH: (-0.35, 0.0)}
    )  # straight ahead of the start pose, in plain sight, but four rows away
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)})
    left_from = None
    while mission.state not in (State.DONE, State.FAILED) and mission.now < 600:
        before = mission.state
        mission.step()
        if before is State.SWEEP and mission.state is State.APPROACH:
            left_from = (mission.odometry.x, mission.odometry.y)
    assert mission.state is State.DONE and len(world.delivered) == 1
    assert left_from is not None and left_from[0] > 0.4  # it kept vacuuming until the can was on its way
    assert math.dist(left_from, (1.4, 0.0)) <= 1.0 + 0.05
    assert mission.map.objects[0].status == "delivered"  # and it was on the map from the start


def test_without_a_pickup_range_the_vacuum_goes_for_anything_in_sight():
    world = SimWorld(
        objects=[SimObject(1.4, 0.0, Category.TRASH, "can")], stations={Category.TRASH: (-0.35, 0.0)}
    )
    mission = build(world, stations={Category.TRASH: Station(-0.35, 0.0)}, pickup_range_m=0.0)
    mission.step()
    assert mission.state is State.APPROACH  # at once, from the start pose


def test_the_scan_route_runs_down_the_middle_of_wide_strips():
    assert scan_waypoints(Room(length_m=2.0, width_m=1.6, margin_m=0.0), 1.6) == [(0.0, 0.0), (1.7, 0.0)]
    two = scan_waypoints(ROOM, 1.6)  # 1.8 m wide: two strips of 0.9 m
    assert two == [(0.0, -0.45), (2.1, -0.45), (2.1, 0.45), (0.0, 0.45)]
    off = scan_waypoints(Room(length_m=2.0, width_m=1.2, margin_m=0.0, y_offset_m=0.3), 1.6)
    assert off == [(0.0, 0.3), (1.7, 0.3)]  # an off-centre zone: down its own middle


def test_for_use_picks_the_route_of_each_use():
    cfg = SweepConfig(room=ROOM)
    assert for_use(cfg, "vacuum").pattern == "rows" and for_use(cfg, "scan").pattern == "scan"
    lanes = SweepConfig(room=ROOM, pattern="lanes")  # the earlier vacuum path, kept when asked for
    assert for_use(lanes, "vacuum").pattern == "lanes" and for_use(lanes, "scan").pattern == "scan"
    assert for_use(for_use(cfg, "scan"), "vacuum").pattern == "rows"
    with pytest.raises(ValueError, match="use"):
        for_use(cfg, "mop")


def test_scanning_it_looks_left_and_right_and_fetches_what_it_spots():
    world = sweep_world()
    mission = build(world, pattern="scan", slip=0.04, yaw_drift=0.03)
    swings, far = [], 0.0
    while mission.state not in (State.DONE, State.FAILED) and mission.now < 1500:
        before = mission.state
        mission.step()
        if before is State.SWEEP and mission.state is State.SWEEP:
            swings.append(math.degrees(math.asin(math.sin(mission.odometry.yaw - mission._course))))
        if before is State.SWEEP and mission.state is State.APPROACH:
            far = max(far, mission._track.distance_m)
    assert mission.state is State.DONE and world.objects == []
    assert sorted((o.label, s.value) for o, s in world.delivered) == [
        ("can", "trash"), ("can", "trash"), ("sock", "clothing"), ("sock", "clothing"),
    ]  # fmt: skip
    assert max(swings) > 30 and min(swings) < -30  # the heading swings to both sides of the way it drives
    assert far > 1.0  # it goes for things beyond the vacuum's reach
    shot = mission.snapshot()
    assert shot["use"] == "scan" and shot["pattern"] == "scan" and len(shot["waypoints"]) == 4
    assert math.hypot(world.x, world.y) < 0.06


def test_scanning_an_empty_zone_the_swings_cancel_out():
    world = SimWorld(stations={Category.TRASH: (-0.35, 0.0)}, station_facing={Category.TRASH: 0.0})
    room = Room(length_m=2.0, width_m=1.6, margin_m=0.0)  # one lane down the middle
    mission = build(
        world, stations={Category.TRASH: Station(-0.35, 0.0)}, room=room, pattern="scan", slip=0.04
    )
    while mission.state is State.SWEEP and mission.now < 300:
        mission.step()
    assert mission.state is State.RETURN_HOME
    assert world.x == pytest.approx(1.7 * 0.96, abs=0.06)  # at the end of the lane (the wheels slip 4 %)
    assert abs(world.y) < 0.05  # and still on it: what slipped turning left was undone turning right
    assert mission.map.coverage > 0.9


def test_a_noisy_speed_reading_after_a_pick_does_not_turn_the_map():
    """On the robot, a wheel that stands still reads 50 steps/s one frame in four. The mission
    used to integrate that reading over the whole pick: up to 9 degrees of heading, for nothing."""
    from makai.contracts import BaseVelocity

    class NoisyAtRest(SimRobot):
        def get_observation(self):
            obs = super().get_observation()
            if self._vel.is_zero():
                obs.base_velocity = BaseVelocity(theta=math.radians(0.586))  # one wheel at 50 steps/s
            return obs

    world = SimWorld(
        objects=[SimObject(0.7, 0.0, Category.TRASH, "can")],
        stations={Category.TRASH: (-0.35, 0.0)},
        station_facing={Category.TRASH: 0.0},
    )
    cfg = MissionConfig()
    pick = SimPick(world, goal_xy=(cfg.approach.goal_x_m, cfg.approach.goal_y_m))
    grab = pick.run

    def fifteen_seconds(robot, target):
        world.time += 15.0  # a real pick lasts 8 to 20 s, base stopped
        return grab(robot, target)

    pick.run = fifteen_seconds
    mission = SweepMission(
        NoisyAtRest(world),
        SimPerception(world, station_max_range_m=1.2, max_range_m=1.5),
        pick,
        SimDrop(world),
        cfg,
        SweepConfig(room=ROOM, stations={Category.TRASH: Station(-0.35, 0.0)}),
    )
    before = None
    while mission.state is not State.DOCK and mission.now < 120:
        before = mission.odometry.yaw
        mission.step()
    assert mission.state is State.DOCK and mission.carrying is Category.TRASH
    mission.step()  # the first step after the pick: 15 s after the one before
    assert abs(math.degrees(mission.odometry.yaw - before)) < 0.2


# ---------------------------------------------------------------- the bin across the zone
ACROSS = {Category.TRASH: Station(2.35, 0.0, 2.0, 0.0)}  # 2.35 m ahead of the start pose, facing it


def facing(slip=0.0, yaw_drift=0.0, marker_range=2.5, **more) -> tuple[SweepMission, SimWorld]:
    world = facing_world()
    cfg = MissionConfig()
    mission = SweepMission(
        SimRobot(world, slip=slip, yaw_drift=yaw_drift),
        SimPerception(world, station_max_range_m=marker_range, max_range_m=1.5),
        SimPick(world, goal_xy=(cfg.approach.goal_x_m, cfg.approach.goal_y_m)),
        SimDrop(world),
        cfg,
        SweepConfig(room=Room(length_m=2.0, width_m=1.6, margin_m=0.0), stations=ACROSS, **more),
    )
    return mission, world


def run_and_watch(mission: SweepMission, world: SimWorld) -> tuple[float, float]:
    """Run to the end. Returns how much the base was told to turn in all (degrees), and the
    largest gap between where the odometry put the robot and where it really was (metres)."""
    turned = gap = 0.0
    while mission.state not in (State.DONE, State.FAILED) and mission.now < 1500:
        mission.step()
        turned += abs(mission.robot._vel.theta) * mission.robot.dt
        gap = max(gap, math.hypot(world.x - mission.odometry.x, world.y - mission.odometry.y))
    return math.degrees(turned), gap


def test_with_the_bin_across_the_zone_the_robot_never_turns():
    mission, world = facing()
    turned, gap = run_and_watch(mission, world)
    assert mission.state is State.DONE and world.objects == [] and len(world.delivered) == 4
    assert turned == 0.0  # not once in the whole mission: sweeping, fetching, delivering, coming back
    assert gap < 0.02
    assert mission.events[-1].reason == "zone swept, back at the start"
    assert math.hypot(world.x, world.y) < 0.05 and abs(world.yaw) < 1e-6
    assert mission.snapshot()["stations"]["trash"] == {"x": 2.35, "y": 0.0, "dock_x": 2.0, "dock_y": 0.0}


def test_the_marker_in_view_holds_the_odometry_all_along():
    mission, world = facing(slip=0.04, yaw_drift=0.03)
    turned, gap = run_and_watch(mission, world)
    assert mission.state is State.DONE and len(world.delivered) == 4
    assert gap < 0.08  # never more than a few centimetres off, over the whole mission
    assert turned < 90  # only small corrections to stay square to the marker
    assert math.hypot(world.x, world.y) < 0.05 and abs(math.degrees(world.yaw)) < 6

    blind, blind_world = facing(slip=0.04, yaw_drift=0.03, marker_fix_gain=0.0)  # the same, camera unused
    for obj in list(blind_world.objects):
        blind_world.objects.remove(obj)  # nothing to deliver: the marker is never visited either
    _, blind_gap = run_and_watch(blind, blind_world)
    assert blind_gap > 0.2  # what the wheels alone make of it


def test_the_direction_of_the_marker_corrects_the_heading_and_its_distance_the_position():
    mission, _ = facing()
    mission.state = State.SWEEP
    # The robot really is at (0.5, 0.2), facing the bin. Its odometry is 12 degrees and 10 cm off.
    mission.odometry.x, mission.odometry.y, mission.odometry.yaw = 0.6, 0.2, math.radians(12.0)
    seen = Scene(stations={Category.TRASH: StationSighting(Category.TRASH, 2.35 - 0.5, 0.0 - 0.2)})
    for _ in range(60):  # two seconds of images
        mission._fix_on_markers(seen)
    assert abs(math.degrees(mission.odometry.yaw)) < 1.0
    assert mission.odometry.x == pytest.approx(0.5, abs=0.02) and mission.odometry.y == pytest.approx(
        0.2, abs=0.03
    )
    assert mission.locked_at is not None

    before = (mission.odometry.x, mission.odometry.y, mission.odometry.yaw)
    wild = Scene(stations={Category.TRASH: StationSighting(Category.TRASH, 0.9, 1.4)})  # a wrong reading
    far = Scene(stations={Category.TRASH: StationSighting(Category.TRASH, 3.4, 0.0)})  # too far to trust
    unknown = Scene(stations={Category.CLOTHING: StationSighting(Category.CLOTHING, 1.0, 0.0)})  # not placed
    for scene in (wild, far, unknown):
        mission._fix_on_markers(scene)
    assert (mission.odometry.x, mission.odometry.y, mission.odometry.yaw) == before


def test_close_to_the_marker_the_heading_is_left_to_the_dock():
    mission, _ = facing()
    mission.state = State.DOCK
    mission.odometry.x, mission.odometry.y, mission.odometry.yaw = (
        1.8,
        0.05,
        0.0,
    )  # 5 cm to the side, 0.55 m away
    seen = Scene(stations={Category.TRASH: StationSighting(Category.TRASH, 0.55, 0.0)})
    for _ in range(30):
        mission._fix_on_markers(seen)
    assert mission.odometry.yaw == 0.0  # 5 cm at 0.55 m would have passed for 5 degrees of heading
