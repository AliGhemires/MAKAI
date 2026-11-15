"""Entry point: run the tidy-up mission, in simulation or on the robot.

uv run makai-mission --sim            # no hardware needed
uv run makai-mission --sim --sweep    # a robot vacuum: rows over the whole floor, picks up what lies on its way
uv run makai-mission --sim --sweep --use scan   # a patrol: looks left and right, goes to whatever it spots
uv run makai-mission --sweep          # real robot, settings from configs/
"""

from __future__ import annotations

import argparse
import logging

from makai.config import load_config
from makai.contracts import Category
from makai.navigation.approach import ApproachConfig
from makai.orchestrator.mission import Mission, MissionConfig, State


def build_sim(mission_cfg: MissionConfig, pick_success: float) -> tuple[Mission, object]:
    from makai.sim.world import SimDrop, SimPerception, SimPick, SimRobot, demo_world

    world = demo_world()
    goal = (mission_cfg.approach.goal_x_m, mission_cfg.approach.goal_y_m)
    mission = Mission(
        SimRobot(world),
        SimPerception(world, station_max_range_m=5.0),
        SimPick(world, goal_xy=goal, success_rate=pick_success),
        SimDrop(world),
        mission_cfg,
    )
    return mission, world


def build_sweep_sim(
    mission_cfg: MissionConfig, pick_success: float, slip: float = 0.04, use: str = "vacuum"
) -> tuple[Mission, object]:
    """The sweeping mission in a simulated room, with wheels that slip a little."""
    from makai.navigation.coverage import Room
    from makai.orchestrator.sweep import Station, SweepConfig, SweepMission, for_use
    from makai.sim.world import SimDrop, SimPerception, SimPick, SimRobot, sweep_world

    world = sweep_world()
    goal = (mission_cfg.approach.goal_x_m, mission_cfg.approach.goal_y_m)
    stations = {Category.TRASH: Station(-0.35, 0.0), Category.CLOTHING: Station(-0.35, 0.7, 0.0, 0.7)}
    mission = SweepMission(
        SimRobot(world, slip=slip, yaw_drift=0.75 * slip),
        SimPerception(world, station_max_range_m=1.2, max_range_m=1.5),
        SimPick(world, goal_xy=goal, success_rate=pick_success),
        SimDrop(world),
        mission_cfg,
        for_use(SweepConfig(room=Room(length_m=2.4, width_m=1.8), stations=stations), use),
    )
    return mission, world


def build_real(cfg: dict, mission_cfg: MissionConfig, sweep: bool = False, use: str = "vacuum") -> Mission:
    # Imported lazily: needs the `robot` and `perception` extras.
    from makai.manipulation.skills import build_drop_skill, build_pick_skill
    from makai.perception.pipeline import build_perception
    from makai.robot.lekiwi import LeKiwiRobot

    robot = LeKiwiRobot.from_config(cfg)
    robot.connect()
    parts = (robot, build_perception(cfg), build_pick_skill(cfg), build_drop_skill(cfg), mission_cfg)
    if not sweep:
        return Mission(*parts)
    from makai.orchestrator.sweep import SweepMission, for_use

    return SweepMission(*parts, for_use(sweep_config(cfg), use))


def sweep_config(cfg: dict):
    """`navigation.sweep` of the config: the room, the route, where the stations stand."""
    from makai.navigation.coverage import Room
    from makai.navigation.zone import load_zone
    from makai.orchestrator.sweep import Station, SweepConfig

    sweep = dict(cfg.get("navigation", {}).get("sweep", {}))
    configured = sweep.pop("room", {})
    room = Room(**(load_zone() or configured))  # a zone traced with the robot replaces the config's
    stations = {Category(name): Station(**place) for name, place in sweep.pop("stations", {}).items()}
    if "marker_scan_deg" in sweep:
        sweep["marker_scan_deg"] = tuple(sweep["marker_scan_deg"])
    return SweepConfig(room=room, **({"stations": stations} if stations else {}), **sweep)


def mission_config(cfg: dict) -> MissionConfig:
    nav = cfg.get("navigation", {})
    return MissionConfig(approach=ApproachConfig(**nav.get("approach", {})), **nav.get("mission", {}))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sim", action="store_true", help="run in the 2D simulator (no hardware)")
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="sweep the room in rows, like a vacuum, instead of looking around",
    )
    parser.add_argument(
        "--use",
        choices=("vacuum", "scan"),
        default="vacuum",
        help="with --sweep. vacuum: pass over the whole floor, pick up what lies on the way. "
        "scan: patrol the zone looking left and right, go to whatever is spotted",
    )
    parser.add_argument("--pick-success", type=float, default=0.8, help="simulated grasp success rate")
    parser.add_argument("--max-duration", type=float, default=600.0, help="seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = load_config()
    mission_cfg = mission_config(cfg)
    if args.sim:
        if args.sweep:
            mission, world = build_sweep_sim(mission_cfg, args.pick_success, use=args.use)
        else:
            mission, world = build_sim(mission_cfg, args.pick_success)
        final = mission.run(max_duration_s=args.max_duration)
        for obj, station in world.delivered:
            mark = "ok" if obj.category is station else "WRONG STATION"
            print(f"  {obj.label:12s} -> {station.value:9s} {mark}")
    else:
        mission = build_real(cfg, mission_cfg, sweep=args.sweep, use=args.use)
        final = mission.run(max_duration_s=args.max_duration, rate_hz=cfg["robot"]["fps"])
        mission.robot.disconnect()

    print(f"Mission {final.value}: {mission.stats}")
    if args.sweep:
        pose = mission.odometry
        print(
            f"  floor covered by the camera: {mission.map.coverage:.0%}, back at ({pose.x:+.2f}, {pose.y:+.2f}) m"
        )
    raise SystemExit(0 if final is State.DONE else 1)


if __name__ == "__main__":
    main()
