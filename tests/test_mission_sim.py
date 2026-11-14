"""End-to-end: the real state machine and navigation, on the simulated robot."""

from makai.contracts import Category
from makai.orchestrator.mission import Mission, MissionConfig, State
from makai.sim.world import SimDrop, SimObject, SimPerception, SimPick, SimRobot, SimWorld, demo_world


def build(
    world: SimWorld,
    pick_success: float = 1.0,
    cfg: MissionConfig | None = None,
    min_range_m: float = 0.12,
    classify_range_m: float | None = None,
) -> Mission:
    cfg = cfg or MissionConfig()
    goal = (cfg.approach.goal_x_m, cfg.approach.goal_y_m)
    return Mission(
        SimRobot(world),
        SimPerception(
            world, station_max_range_m=5.0, min_range_m=min_range_m, classify_range_m=classify_range_m
        ),
        SimPick(world, goal_xy=goal, success_rate=pick_success),
        SimDrop(world),
        cfg,
    )


def test_tidies_the_whole_room():
    world = demo_world()
    mission = build(world)
    assert mission.run(max_duration_s=600) is State.DONE
    assert world.objects == [] and world.carrying is None
    assert len(world.delivered) == 4
    assert all(obj.category is station for obj, station in world.delivered)
    assert mission.stats.delivered == 4


def test_retries_failed_grasps():
    world = demo_world()
    mission = build(world, pick_success=0.6)
    assert mission.run(max_duration_s=900) is State.DONE
    assert mission.stats.delivered == 4
    assert mission.stats.failed_picks > 0


def test_empty_room_finishes_quickly():
    world = SimWorld(stations={Category.TRASH: (2.0, 0.0)})
    mission = build(world)
    assert mission.run(max_duration_s=60) is State.DONE
    assert mission.stats.picked == 0


def test_fails_cleanly_when_station_is_missing():
    world = SimWorld(objects=[SimObject(1.0, 0.0, Category.TRASH, "can")])
    mission = build(world)
    assert mission.run(max_duration_s=120) is State.FAILED
    assert "station" in mission.events[-1].reason


def test_unknown_objects_are_left_alone():
    world = SimWorld(
        objects=[SimObject(1.0, 0.0, Category.UNKNOWN, "shoe")], stations={Category.TRASH: (2.0, 1.0)}
    )
    mission = build(world)
    assert mission.run(max_duration_s=60) is State.DONE
    assert len(world.objects) == 1


def test_last_mile_on_odometry_when_the_camera_cannot_see_close_objects():
    """Front camera blind below 35 cm, pre-grasp pose at 22 cm: the end of the approach is dead-reckoned."""
    world = demo_world()
    mission = build(world, min_range_m=0.35)
    assert mission.run(max_duration_s=600) is State.DONE
    assert mission.stats.delivered == 4 and mission.stats.failed_picks == 0


def test_category_is_decided_up_close_not_from_far_away():
    """From afar everything is guessed to be clothing; the real category is only known within 60 cm,
    and the camera loses the object below 35 cm. Each object must still reach the right station."""
    world = demo_world()
    mission = build(world, min_range_m=0.35, classify_range_m=0.6)
    assert mission.run(max_duration_s=600) is State.DONE
    assert len(world.delivered) == 4
    assert all(obj.category is station for obj, station in world.delivered)
    # The category changing on the way must not make the robot lose its target.
    assert not any("lost" in event.reason for event in mission.events)
