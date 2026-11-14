"""Arm skills: what happens once navigation has put the robot in the right place.

- `ScriptedSequence`: play named arm poses one after the other. Used for the drop
  (no learning needed) and as the fallback pick if the policy is not ready.
- `PolicyPick`: run the learned policy with the base frozen.

Poses live in configs/arm_poses.yaml and are captured on the robot with
`scripts/teleop.py` (press `p` to save the current pose).
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from makai.config import CONFIG_DIR
from makai.contracts import Category, Robot, Target

Pose = Mapping[str, float]
GRIPPER = "arm_gripper.pos"


def load_poses(path: str | Path) -> dict[str, dict[str, float]]:
    return yaml.safe_load(Path(path).read_text()) or {}


def move_to(
    robot: Robot, pose: Pose, duration_s: float = 1.5, rate_hz: float = 30.0, sleep=time.sleep
) -> None:
    """Move the arm to `pose` along a straight line in joint space, with a smooth start and stop."""
    start = robot.get_observation().arm
    steps = max(1, int(duration_s * rate_hz))
    for i in range(1, steps + 1):
        s = i / steps
        blend = s * s * (3 - 2 * s)  # smoothstep
        robot.move_arm(
            {key: start.get(key, goal) + (goal - start.get(key, goal)) * blend for key, goal in pose.items()}
        )
        sleep(1.0 / rate_hz)


class ScriptedSequence:
    """Play poses in order. Each step is a pose name or (pose name, seconds)."""

    def __init__(
        self,
        poses: Mapping[str, Pose],
        steps: Sequence[str | tuple[str, float]],
        rate_hz: float = 30.0,
        sleep=time.sleep,
    ):
        self.poses, self.rate_hz, self.sleep = poses, rate_hz, sleep
        self.steps = [(s, 1.5) if isinstance(s, str) else (s[0], float(s[1])) for s in steps]
        missing = [name for name, _ in self.steps if name not in poses]
        if missing:
            raise KeyError(f"poses not defined in arm_poses.yaml: {missing}")

    def play(self, robot: Robot) -> None:
        robot.stop()
        for name, duration in self.steps:
            move_to(robot, self.poses[name], duration, self.rate_hz, self.sleep)


class ScriptedPick:
    """Open-loop grasp. Works only because navigation always puts the object at the same spot."""

    def __init__(self, sequence: ScriptedSequence):
        self.sequence = sequence

    def run(self, robot: Robot, target: Target) -> bool:
        self.sequence.play(robot)
        return True  # no feedback: the mission finds the object again if the grasp missed


class ScriptedDrop:
    def __init__(self, sequences: Mapping[Category, ScriptedSequence]):
        self.sequences = sequences

    def run(self, robot: Robot, category: Category) -> bool:
        self.sequences[category].play(robot)
        return True


class PolicyPick:
    """Run a LeRobot policy on the arm for a fixed time, base frozen, then go to the carry pose.

    Follows lerobot 0.7.0 `examples/lekiwi/evaluate.py`. Needs the real `LeKiwiRobot`.
    """

    def __init__(
        self,
        policy_type: str,
        policy_path: str,
        task: str,
        duration_s: float,
        fps: int,
        device: str | None = None,
        after: ScriptedSequence | None = None,
        gripper_open_above: float | None = None,
    ):
        import torch
        from lerobot.policies import get_policy_class, make_pre_post_processors

        self.task, self.duration_s, self.fps, self.after = task, duration_s, fps, after
        self.gripper_open_above = gripper_open_above
        self.policy = get_policy_class(policy_type).from_pretrained(policy_path)
        if device:
            self.policy.to(device)
            self.policy.config.device = device
        self.device = torch.device(self.policy.config.device)
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg=self.policy.config,
            pretrained_path=policy_path,
            preprocessor_overrides={"device_processor": {"device": str(self.device)}},
        )
        self._features = None

    def run(self, robot: Robot, target: Target) -> bool:
        from lerobot.common.control_utils import predict_action
        from lerobot.policies.utils import make_robot_action
        from lerobot.utils.constants import ACTION, OBS_STR
        from lerobot.utils.feature_utils import build_dataset_frame, hw_to_dataset_features

        client = robot.client  # LeKiwiRobot only
        if self._features is None:
            self._features = {
                **hw_to_dataset_features(client.action_features, ACTION),
                **hw_to_dataset_features(client.observation_features, OBS_STR),
            }
        self.policy.reset()
        stop = {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
        start = time.perf_counter()
        while time.perf_counter() - start < self.duration_s:
            tick = time.perf_counter()
            robot.get_observation()
            frame = build_dataset_frame(self._features, robot.raw_observation, prefix=OBS_STR)
            action = predict_action(
                observation=frame,
                policy=self.policy,
                device=self.device,
                preprocessor=self.preprocessor,
                postprocessor=self.postprocessor,
                use_amp=self.device.type == "cuda",
                task=self.task,
                robot_type=client.name,
            )
            # The policy was trained with the base still: never let it drive.
            client.send_action({**make_robot_action(action, self._features), **stop})
            time.sleep(max(0.0, 1.0 / self.fps - (time.perf_counter() - tick)))

        gripper = robot.get_observation().arm.get(GRIPPER)
        if self.after:
            self.after.play(robot)
        if self.gripper_open_above is None or gripper is None:
            return True
        # A gripper that could not close completely is holding something.
        return gripper > self.gripper_open_above


def build_pick_skill(cfg: dict):
    m = cfg["manipulation"]
    poses = load_poses(CONFIG_DIR / m["poses_file"])
    pick = m["pick"]
    if pick["kind"] == "scripted":
        return ScriptedPick(ScriptedSequence(poses, pick["steps"], cfg["robot"]["fps"]))
    after = ScriptedSequence(poses, pick["after"], cfg["robot"]["fps"]) if pick.get("after") else None
    return PolicyPick(
        pick["policy_type"],
        pick["policy_path"],
        pick["task"],
        pick["duration_s"],
        cfg["robot"]["fps"],
        pick.get("device"),
        after,
        pick.get("gripper_open_above"),
    )


def build_drop_skill(cfg: dict) -> ScriptedDrop:
    m = cfg["manipulation"]
    poses = load_poses(CONFIG_DIR / m["poses_file"])
    return ScriptedDrop(
        {Category(c): ScriptedSequence(poses, steps, cfg["robot"]["fps"]) for c, steps in m["drop"].items()}
    )
