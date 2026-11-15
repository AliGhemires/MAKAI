"""The sweeping mission, end to end on the simulated robot, and the pieces it is made of."""

import math

import pytest

from makai.contracts import Category
from makai.navigation.coverage import Room, path_length_m, snake_waypoints
from makai.navigation.mapping import RoomMap
from makai.orchestrator.mission import MissionConfig, State
from makai.orchestrator.sweep import Station, SweepConfig, SweepMission
from makai.sim.world import SimDrop, SimObject, SimPerception, SimPick, SimRobot, SimWorld, sweep_world

ROOM = Room(length_m=2.4, width_m=1.8)
TWO_STATIONS = {Category.TRASH: Station(-0.35, 0.0), Category.CLOTHING: Station(-0.35, 0.7, 0.0, 0.7)}


def build(
    world: SimWorld, stations=None, pick_success=1.0, slip=0.0, yaw_drift=0.0, room=ROOM
) -> SweepMission:
    cfg = MissionConfig()
    return SweepMission(
        SimRobot(world, slip=slip, yaw_drift=yaw_drift),
        SimPerception(world, station_max_range_m=1.2, max_range_m=1.5),
        SimPick(world, goal_xy=(cfg.approach.goal_x_m, cfg.approach.goal_y_m), success_rate=pick_success),
        SimDrop(world),
        cfg,
        SweepConfig(room=room, stations=stations or TWO_STATIONS),
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


def test_sweeps_the_room_and_tidies_everything():
    world = sweep_world()
    mission = build(world)
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
    assert shot["waypoints"][0] == [0.3, -0.6] and "trash" in shot["stations"]


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
    assert math.hypot(world.x, world.y) < 0.05  # heavy drift, and still back at the origin
