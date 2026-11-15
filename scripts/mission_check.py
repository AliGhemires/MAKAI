"""Before going to the robot: does the sweeping mission start from this laptop's configuration?

    uv run python scripts/mission_check.py
    uv run python scripts/mission_check.py --policy outputs/train/act_can_v1/checkpoints/last/pretrained_model

Builds the REAL mission exactly as the console does (detector, floor calibration, station
markers, pick policies, drop poses, room and stations of `navigation.sweep`), on a stand-in
robot that returns test images, and runs it for three seconds. A missing model, calibration or
pose shows up here, with its name, instead of in front of the jury.

It proves nothing about how the robot behaves: the stand-in does not move and sees nothing.
"""

from __future__ import annotations

import argparse
import time

from makai.app import mission_config, sweep_config
from makai.config import load_config
from makai.manipulation.skills import build_drop_skill, build_pick_skill
from makai.orchestrator.sweep import SweepMission
from makai.perception.pipeline import build_perception
from makai.robot.fake import FakeKiwi
from makai.robot.lekiwi import LeKiwiRobot, make_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--policy", help="try this checkpoint instead of manipulation.pick.policy_path")
    parser.add_argument("--device", help="default: manipulation.pick.device; 'mps' on the Macs")
    args = parser.parse_args()

    cfg = load_config()
    pick = cfg["manipulation"]["pick"]
    if args.policy:
        pick["policy_path"] = args.policy
    if args.device:
        pick["device"] = args.device
    robot = LeKiwiRobot(FakeKiwi(make_client(cfg).config), tuple(cfg["robot"]["cameras"]))
    robot.connect()

    start = time.perf_counter()
    mission = SweepMission(
        robot,
        build_perception(cfg),
        build_pick_skill(cfg),
        build_drop_skill(cfg),
        mission_config(cfg),
        sweep_config(cfg),
    )
    room = mission.sweep.room
    print(f"[ok  ] mission built in {time.perf_counter() - start:.1f} s")
    print(f"       room {room.length_m} x {room.width_m} m, {(len(mission.waypoints) + 1) // 2} {mission.sweep.pattern}, stations: "
          + ", ".join(f"{key.value} at ({s.x:+.2f}, {s.y:+.2f})" for key, s in mission.sweep.stations.items()))  # fmt: skip
    print(
        f"       pick skill: {type(mission.pick).__name__}; detector: {cfg['perception']['learned']['weights']}"
    )

    fps = cfg["robot"]["fps"]
    start = time.perf_counter()
    for _ in range(3 * fps):
        mission.step()
    step_ms = 1000 * (time.perf_counter() - start) / (3 * fps)
    verdict = "ok  " if step_ms < 1000 / fps else "WARN"
    print(
        f"[{verdict}] one step of the mission takes {step_ms:.0f} ms on this laptop (the robot needs under {1000 / fps:.0f} ms)"
    )
    poses = mission.drop.sequences if hasattr(mission.drop, "sequences") else {}
    zero = sorted(
        {
            name
            for seq in poses.values()
            for name, _ in seq.steps
            if not any(abs(v) > 1e-6 for v in seq.poses[name].values())
        }
    )
    if zero:
        print(
            f"[WARN] arm poses still at zero in configs/arm_poses.yaml: {zero}. The drop would send the arm there."
        )
    robot.disconnect()
    print(
        "Ready to try on the robot. This check did not move anything and proves nothing about the robot itself."
    )


if __name__ == "__main__":
    main()
