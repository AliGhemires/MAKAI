"""Run a trained pick policy on the robot, once or several times, and keep the score.

    uv run python scripts/try_pick.py --policy outputs/train/act_sock_v1/checkpoints/last/pretrained_model --trials 10
    uv run python scripts/try_pick.py --policy <namespace>/makai_act_sock_v1 --trials 10      # from the Hub
    uv run python scripts/try_pick.py --policy <namespace>/makai_act_sock_v1 --revision 020000 --trials 10
    uv run python scripts/try_pick.py --policy <path> --n-action-steps 30 --trials 10        # more reactive
    uv run python scripts/try_pick.py --policy <path> --dry-run                               # no hardware

Each trial: the arm opens its hand and goes to its home pose by itself (the pose every
demonstration starts from, `home` in configs/arm_poses.yaml). Put the object in the pre-grasp
zone, hands away, press Enter: the policy runs. Then answer y / n: was the object held?
At the end, the gripper readings of the held and the empty trials give the value to put in
manipulation.pick.gripper_open_above, so that the mission notices an empty grasp and retries.
The base never moves (its velocities are forced to zero). Keep a hand near the power switch
the first time a new model runs.

Write the result in docs/REGISTRY.md: it decides which model goes in the demo.
"""

from __future__ import annotations

import argparse
import time

from makai.config import CONFIG_DIR, load_config
from makai.contracts import Category, Target
from makai.manipulation.skills import GRIPPER, PolicyPick, load_poses, move_to
from makai.robot.lekiwi import LeKiwiRobot, make_client

OPEN_GRIPPER = 35.0  # the widest opening in the demonstrations: lets go of the object between trials


def grasp_check(readings: list[tuple[bool, float]]) -> str:
    """From (held?, gripper at the end) of each trial: the setting that lets the mission notice an
    empty grasp and try again. A gripper that could not close completely is holding something."""
    held = [value for ok, value in readings if ok]
    empty = [value for ok, value in readings if not ok]
    if not held or not empty:
        seen = ", ".join(f"{value:.1f}" for _, value in readings) or "none"
        return (
            f"Gripper at the end of the trials: {seen}. To set the grasp check, one trial with the "
            "object held and one with an empty hand are needed."
        )
    spread = f"held {min(held):.1f} to {max(held):.1f}, empty {min(empty):.1f} to {max(empty):.1f}"
    if min(held) <= max(empty):
        return f"Gripper at the end: {spread}. They overlap: the gripper alone cannot tell an empty grasp."
    return (
        f"Gripper at the end: {spread}. In configs/makai.yaml set manipulation.pick.gripper_open_above: "
        f"{(min(held) + max(empty)) / 2:.1f} and the mission tries again after an empty grasp."
    )


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
        "--revision", default=None, help="checkpoint of a Hub repo, by step: 010000, 020000..."
    )
    parser.add_argument("--n-action-steps", type=int, default=None,
                        help="actions played before looking again (default: as trained, 100 = 3.3 s). Try 30")  # fmt: skip
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
        n_action_steps=args.n_action_steps,
        revision=args.revision,
    )
    print(f"Policy loaded in {time.perf_counter() - start:.1f} s on {skill.device}")

    home = load_poses(CONFIG_DIR / cfg["manipulation"]["poses_file"])["home"]
    robot.connect()
    successes = 0
    readings: list[tuple[bool, float]] = []
    try:
        for trial in range(1, args.trials + 1):
            if not args.dry_run:
                input(
                    f"\nTrial {trial}/{args.trials}: the arm will open its hand, then go to its home pose. "
                    "Keep clear of it. Enter to go..."
                )
            # The policy was trained from the home pose, hand closed: start every trial there.
            move_to(robot, {GRIPPER: OPEN_GRIPPER}, 0.8)
            move_to(robot, home, 3.0 if trial == 1 else 2.0)
            if not args.dry_run:
                input("Object in the zone, hands away. Enter to start the policy...")
            skill.run(robot, Target(Category.UNKNOWN, "object", 0.0, 0.0))
            robot.stop()
            grip = skill.last_gripper
            rate = f"{skill.last_rate_hz:.1f} commands per second (target {cfg['robot']['fps']})"
            rate += "" if grip is None else f". Gripper at the end: {grip:.1f}"
            if args.dry_run:
                print(f"Trial {trial}: {rate}")
            else:
                held = input(f"{rate}. Object held at the end? [y/n] ").strip().lower().startswith("y")
                successes += held
                if grip is not None:
                    readings.append((held, grip))
    finally:
        robot.disconnect()
    if not args.dry_run:
        print(f"\nRESULT: {successes}/{args.trials} for {args.policy}")
        print(grasp_check(readings))


if __name__ == "__main__":
    main()
