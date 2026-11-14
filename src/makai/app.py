"""Entry point: run the tidy-up mission, in simulation or on the robot.

uv run makai-mission --sim          # no hardware needed
uv run makai-mission                # real robot, settings from configs/
"""

from __future__ import annotations

import argparse
import logging

from makai.config import load_config
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


def build_real(cfg: dict, mission_cfg: MissionConfig) -> Mission:
    # Imported lazily: needs the `robot` and `perception` extras.
    from makai.manipulation.skills import build_drop_skill, build_pick_skill
    from makai.perception.pipeline import build_perception
    from makai.robot.lekiwi import LeKiwiRobot

    robot = LeKiwiRobot.from_config(cfg)
    robot.connect()
    return Mission(robot, build_perception(cfg), build_pick_skill(cfg), build_drop_skill(cfg), mission_cfg)


def mission_config(cfg: dict) -> MissionConfig:
    nav = cfg.get("navigation", {})
    return MissionConfig(approach=ApproachConfig(**nav.get("approach", {})), **nav.get("mission", {}))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sim", action="store_true", help="run in the 2D simulator (no hardware)")
    parser.add_argument("--pick-success", type=float, default=0.8, help="simulated grasp success rate")
    parser.add_argument("--max-duration", type=float, default=600.0, help="seconds")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    cfg = load_config()
    mission_cfg = mission_config(cfg)
    if args.sim:
        mission, world = build_sim(mission_cfg, args.pick_success)
        final = mission.run(max_duration_s=args.max_duration)
        for obj, station in world.delivered:
            mark = "ok" if obj.category is station else "WRONG STATION"
            print(f"  {obj.label:12s} -> {station.value:9s} {mark}")
    else:
        mission = build_real(cfg, mission_cfg)
        final = mission.run(max_duration_s=args.max_duration, rate_hz=cfg["robot"]["fps"])
        mission.robot.disconnect()

    print(f"Mission {final.value}: {mission.stats}")
    raise SystemExit(0 if final is State.DONE else 1)


if __name__ == "__main__":
    main()
