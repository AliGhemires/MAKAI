"""Check a trained pick policy without the robot: replay recorded episodes through it.

    uv run python scripts/replay_check.py --policy outputs/train/act_sock_v1/checkpoints/last/pretrained_model
    uv run python scripts/replay_check.py --policy <path> --episodes 0,30,58 --control mismatch

The policy is run by `PolicyPick`, the very code the robot runs, on a stand-in robot that
returns the observations of a recorded episode, one per tick. The commands it sends are then
compared with what the pilot commanded at the same instants.

What it proves: the whole inference chain (camera names and order, colours, joint order,
normalisation, action chunks) is the one the model was trained with. A mistake anywhere gives
commands far from the pilot's. What it does not prove: that the policy succeeds on the robot.
The episodes replayed were seen in training, and on the robot the policy's own motion changes
what the cameras see next.

Reading the numbers: "error" is the mean gap, in degrees, between the policy's command and the
pilot's. Compare it with "staying still", the error of an arm that never leaves its first pose.
--control black gives black images; --control mismatch gives the images of another episode
(the object lies elsewhere) with the arm readings of this one. The error must go up: that is
the proof the model looks at the pictures. Swapping the two cameras is NOT a control: ACT gives
every camera the same position code, so it cannot tell which is which and its commands do not
change (measured on 15 Nov: identical to 0.1 degree).

Each run adds a line to outputs/explorations/replay_check.csv (for the slides).
"""

from __future__ import annotations

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from lerobot.datasets import LeRobotDataset
from lerobot.utils.constants import HF_LEROBOT_HOME

from makai.config import REPO_ROOT, load_config
from makai.contracts import Category, Target
from makai.manipulation.skills import PolicyPick
from makai.robot.fake import FakeKiwi
from makai.robot.lekiwi import LeKiwiRobot, make_client

GRIPPER = "arm_gripper.pos"


class ReplayKiwi(FakeKiwi):
    """Returns the observations of a recorded episode, one per tick, and keeps what it is sent."""

    def load(self, observations: list[dict]) -> None:
        self.observations, self.calls, self.sent = observations, 0, []

    def get_observation(self) -> dict:
        # PolicyPick asks once before its clock starts (to warm the model up): the first
        # observation is served twice, so that command k answers observation k.
        index = min(max(self.calls - 1, 0), len(self.observations) - 1)
        self.calls += 1
        return self.observations[index]

    def send_action(self, action: dict) -> dict:
        self.sent.append(dict(action))
        return super().send_action(action)


def as_robot_image(tensor, control: str) -> np.ndarray:
    """A training image (float, channels first) as the robot's camera gives it (uint8, channels last)."""
    image = (tensor.permute(1, 2, 0) * 255).round().clamp(0, 255).byte().numpy()
    return np.zeros_like(image) if control == "black" else image


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--policy", required=True, help="checkpoint folder (…/pretrained_model)")
    parser.add_argument("--dataset", default="pick_sock_v1", help="recorded episodes to replay")
    parser.add_argument("--episodes", default=None, help="comma-separated; default: first, middle, last")
    parser.add_argument("--control", choices=["none", "mismatch", "black"], default="none")
    parser.add_argument("--device", default=None, help="default: as trained; 'mps' on the Macs")
    parser.add_argument("--n-action-steps", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    pick, fps = cfg["manipulation"]["pick"], cfg["robot"]["fps"]
    namespace = cfg["hub"]["namespace"]
    namespace = "local" if namespace == "CHANGE_ME" else namespace
    repo_id = f"{namespace}/makai_{args.dataset}"
    dataset = LeRobotDataset(repo_id, root=Path(HF_LEROBOT_HOME) / repo_id)
    state_names = dataset.meta.features["observation.state"]["names"]
    action_names = dataset.meta.features["action"]["names"]
    cameras = tuple(cfg["robot"]["cameras"])
    total = dataset.meta.total_episodes
    episodes = [int(e) for e in args.episodes.split(",")] if args.episodes else [0, total // 2, total - 1]

    client = ReplayKiwi(make_client(cfg).config)
    robot = LeKiwiRobot(client, cameras)
    skill = PolicyPick(
        pick["policy_type"],
        args.policy,
        pick["task"],
        1.0,
        fps,
        args.device,
        n_action_steps=args.n_action_steps,
    )
    robot.connect()
    arm = [i for i, name in enumerate(action_names) if name.startswith("arm_") and name != GRIPPER]
    grip = action_names.index(GRIPPER)
    rows = []
    print(f"{args.policy}\nreplaying episodes {episodes} of {repo_id}, control: {args.control}")
    recorded = {}
    for episode in episodes:
        meta = dataset.meta.episodes[episode]
        recorded[episode] = [
            dataset[i] for i in range(int(meta["dataset_from_index"]), int(meta["dataset_to_index"]))
        ]
    for position, episode in enumerate(episodes):
        frames = recorded[episode]
        # mismatch: the pictures of the next episode in the list, tick for tick.
        seen = recorded[episodes[(position + 1) % len(episodes)]] if args.control == "mismatch" else frames
        observations = []
        for tick, frame in enumerate(frames):
            observation = dict(zip(state_names, frame["observation.state"].tolist(), strict=True))
            pictures = seen[min(tick, len(seen) - 1)]
            for name in cameras:
                observation[name] = as_robot_image(pictures[f"observation.images.{name}"], args.control)
            observations.append(observation)
        client.load(observations)
        skill.duration_s = len(frames) / fps
        skill.run(robot, Target(Category.UNKNOWN, "object", 0.0, 0.0))

        pilot = np.stack([frame["action"].numpy() for frame in frames])
        count = min(len(client.sent), len(pilot))
        policy = np.array([[sent[name] for name in action_names] for sent in client.sent[:count]])
        gap = np.abs(policy - pilot[:count])
        still = np.abs(pilot[:count] - pilot[0])  # an arm that never leaves its first pose
        row = dict(
            episode=episode,
            ticks=count,
            rate_hz=round(skill.last_rate_hz, 1),
            arm_error_deg=round(float(gap[:, arm].mean()), 2),
            arm_error_p95_deg=round(float(np.percentile(gap[:, arm], 95)), 2),
            gripper_error=round(float(gap[:, grip].mean()), 2),
            arm_still_deg=round(float(still[:, arm].mean()), 2),
            base_command=round(float(np.abs(policy[:, -3:]).max()), 4),
        )
        rows.append(row)
        print(
            f"  episode {episode:>2}: {count} ticks at {row['rate_hz']} Hz | arm error {row['arm_error_deg']:.1f} deg "
            f"(95 % under {row['arm_error_p95_deg']:.1f}) | gripper error {row['gripper_error']:.1f} | "
            f"staying still: {row['arm_still_deg']:.1f} deg | base command {row['base_command']}"
        )
    robot.disconnect()

    error = float(np.mean([row["arm_error_deg"] for row in rows]))
    still = float(np.mean([row["arm_still_deg"] for row in rows]))
    print(
        f"MEAN arm error {error:.1f} deg, against {still:.1f} deg for staying still "
        f"({100 * error / still:.0f} % of it). Control: {args.control}."
    )
    log = REPO_ROOT / "outputs" / "explorations" / "replay_check.csv"
    log.parent.mkdir(parents=True, exist_ok=True)
    new = not log.exists()
    with log.open("a", newline="") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(
                ["when", "policy", "dataset", "episodes", "control", "arm_error_deg", "arm_still_deg", "gripper_error", "rate_hz"]
            )  # fmt: skip
        writer.writerow(
            [
                datetime.now().isoformat(timespec="seconds"),
                args.policy,
                args.dataset,
                " ".join(map(str, episodes)),
                args.control,
                round(error, 2),
                round(still, 2),
                round(float(np.mean([row["gripper_error"] for row in rows])), 2),
                round(float(np.mean([row["rate_hz"] for row in rows])), 1),
            ]
        )
    print(f"logged in {log.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    start = time.perf_counter()
    main()
    print(f"({time.perf_counter() - start:.0f} s)")
