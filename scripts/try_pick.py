"""Run a trained pick policy on the robot, once or several times, and keep the score.

    uv run python scripts/try_pick.py --policy outputs/train/act_sock_v1/checkpoints/last/pretrained_model --trials 10
    uv run python scripts/try_pick.py --policy <namespace>/makai_act_sock_v1 --trials 10      # from the Hub
    uv run python scripts/try_pick.py --policy <path> --dry-run                               # no hardware

Before each trial: put the object in the pre-grasp zone, arm at the home pose, hands away,
then press Enter. After each trial answer y / n: was the object held at the end?
The base never moves (its velocities are forced to zero). Keep a hand near the power switch
the first time a new model runs.

Write the result in docs/REGISTRY.md: it decides which model goes in the demo.
"""

from __future__ import annotations

import argparse
import time

from makai.config import load_config
from makai.contracts import Category, Target
from makai.manipulation.skills import PolicyPick
from makai.robot.lekiwi import LeKiwiRobot, make_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--policy", required=True, help="checkpoint folder (.../pretrained_model) or Hub repo"
    )
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="seconds per trial; default: manipulation.pick.duration_s",
    )
    parser.add_argument("--task", default=None, help="task string, as used when recording")
    parser.add_argument("--device", default=None, help="mps, cuda or cpu; default: as trained")
    parser.add_argument(
        "--dry-run", action="store_true", help="fake robot: check the model loads and runs at speed"
    )
    args = parser.parse_args()

    cfg = load_config()
    pick = cfg["manipulation"]["pick"]
    if args.dry_run:
        from makai.robot.fake import FakeKiwi

        robot = LeKiwiRobot(FakeKiwi(make_client(cfg).config), tuple(cfg["robot"]["cameras"]))
    else:
        robot = LeKiwiRobot.from_config(cfg)

    start = time.perf_counter()
    skill = PolicyPick(
        pick["policy_type"],
        args.policy,
        args.task or pick["task"],
        args.duration or pick["duration_s"],
        cfg["robot"]["fps"],
        args.device,
    )
    print(f"Policy loaded in {time.perf_counter() - start:.1f} s on {skill.device}")

    robot.connect()
    successes = 0
    try:
        for trial in range(1, args.trials + 1):
            if not args.dry_run:
                input(
                    f"\nTrial {trial}/{args.trials}: object in the zone, arm at home, hands away. Enter to start..."
                )
            ticks_before = getattr(robot.client, "_tick", 0)
            start = time.perf_counter()
            skill.run(robot, Target(Category.UNKNOWN, "object", 0.0, 0.0))
            elapsed = time.perf_counter() - start
            robot.stop()
            if args.dry_run:
                rate = (robot.client._tick - ticks_before) / elapsed
                print(f"Trial {trial}: ran {elapsed:.1f} s at {rate:.1f} Hz (target {cfg['robot']['fps']})")
            else:
                successes += input("Object held at the end? [y/n] ").strip().lower().startswith("y")
    finally:
        robot.disconnect()
    if not args.dry_run:
        print(f"\nRESULT: {successes}/{args.trials} for {args.policy}")


if __name__ == "__main__":
    main()
