"""Arm skills: what happens once navigation has put the robot in the right place.

- `ScriptedSequence`: play named arm poses one after the other. Used for the drop
  (no learning needed) and as the fallback pick if the policy is not ready.
- `PolicyPick`: run the learned policy with the base frozen.

Poses live in configs/arm_poses.yaml and are captured on the robot with
`scripts/teleop.py` (press `p` to save the current pose).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from makai.config import CONFIG_DIR
from makai.contracts import Category, Robot, Target

Pose = Mapping[str, float]
GRIPPER = "arm_gripper.pos"
log = logging.getLogger("makai.pick")


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


class BackHome:
    """Has the arm left the pose it started from, and come back to it for good?

    Every demonstration ends that way: the arm returns to its home pose and holds it for one
    second. A pick is therefore over as soon as this is true, not after a fixed time: the
    recorded picks last from 8 to 18 seconds.
    """

    def __init__(self, tol_deg: float = 10.0, hold_s: float = 1.0, fps: float = 30.0):
        self.tol, self.needed = tol_deg, round(hold_s * fps)
        self._start: list[float] | None = None
        self._left, self._held = False, 0

    def update(self, arm: Sequence[float]) -> bool:
        """Feed the arm joints (not the gripper) of one tick. True once the arm is back home."""
        if self._start is None:
            self._start = list(arm)
        gap = max(abs(a - b) for a, b in zip(arm, self._start, strict=True))
        if gap > self.tol:
            self._left, self._held = True, 0
        elif self._left:
            self._held += 1
        return self._left and self._held >= self.needed


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
    """Run a LeRobot policy on the arm until it is back home (at most `duration_s`), base frozen,
    then go to the carry pose.

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
        n_action_steps: int | None = None,
        revision: str | None = None,
    ):
        """`n_action_steps`: how many predicted actions to play before looking at the cameras
        again (the model plans `chunk_size` ahead; default: as trained). Lower is more reactive.
        A free knob: no retraining. `revision`: a checkpoint of a Hub repo, by its step ("010000").
        """
        import torch
        from lerobot.policies import get_policy_class, make_pre_post_processors

        self.task, self.duration_s, self.fps, self.after = task, duration_s, fps, after
        self.gripper_open_above = gripper_open_above
        self.policy = get_policy_class(policy_type).from_pretrained(policy_path, revision=revision)
        if device:
            self.policy.to(device)
            self.policy.config.device = device
        if n_action_steps is not None:
            self.policy.config.n_action_steps = min(n_action_steps, self.policy.config.chunk_size)
        self.device = torch.device(self.policy.config.device)
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg=self.policy.config,
            pretrained_path=policy_path,
            pretrained_revision=revision,
            preprocessor_overrides={"device_processor": {"device": str(self.device)}},
        )
        self._features = None
        self.last_rate_hz = 0.0
        self.gripper_at_stop: float | None = None  # gripper reading when the policy stopped
        self.last_gripper: float | None = None  # the reading the grasp check used (carry pose, if any)

    def run(self, robot: Robot, target: Target) -> bool:
        from lerobot.common.control_utils import predict_action
        from lerobot.policies.utils import make_robot_action
        from lerobot.utils.constants import ACTION, OBS_STR
        from lerobot.utils.feature_utils import build_dataset_frame, hw_to_dataset_features
        from lerobot.utils.robot_utils import precise_sleep

        client = robot.client  # LeKiwiRobot only
        if self._features is None:
            self._features = {
                **hw_to_dataset_features(client.action_features, ACTION),
                **hw_to_dataset_features(client.observation_features, OBS_STR),
            }
        stop = {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
        joints = [key for key in client.action_features if key.endswith(".pos") and key != GRIPPER]
        back_home = BackHome(fps=self.fps)

        def next_action() -> dict:
            robot.get_observation()
            # The demonstrations were recorded with the base still. Whatever the wheels report
            # now (they may still be settling after the approach), show the policy what it saw
            # in training: a base at rest.
            observation = {**robot.raw_observation, **stop}
            frame = build_dataset_frame(self._features, observation, prefix=OBS_STR)
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
            return {**make_robot_action(action, self._features), **stop}

        # The first inference prepares the model for the device and can take a second: do it
        # before the clock starts, and throw the result away.
        next_action()
        self.policy.reset()

        start, ticks = time.perf_counter(), 0
        while time.perf_counter() - start < self.duration_s:
            tick = time.perf_counter()
            client.send_action(next_action())
            ticks += 1
            # Over as soon as the arm is back home, as in the demonstrations; `duration_s` is
            # only the longest a pick may take.
            if back_home.update([float(robot.raw_observation[key]) for key in joints]):
                break
            # time.sleep overshoots by several ms: at 30 Hz that costs 10 % of the rate.
            precise_sleep(max(0.0, 1.0 / self.fps - (time.perf_counter() - tick)))
        # Commands per second actually achieved. Well below `fps`, the motion is slower than
        # the demonstrations: inference is too slow for this laptop.
        self.last_rate_hz = ticks / (time.perf_counter() - start)

        self.gripper_at_stop = robot.get_observation().arm.get(GRIPPER)
        return self._holding(robot)

    def _holding(self, robot: Robot, settle_s: float = 0.4) -> bool:
        """Carry pose, then: is the hand holding something?

        Read once the carry pose (home, hand commanded closed) is reached, not when the policy
        stops: after a missed grasp the policy may come home with its hand still half open, which
        read as "holding" (15 Nov, on the robot). Hand commanded closed is how the recordings end,
        where `gripper_open_above` was measured: an empty hand closes, a held object stops it.
        """
        gripper = self.gripper_at_stop
        if self.after:
            self.after.play(robot)
            time.sleep(settle_s)  # the gripper servo lags its command a little
            gripper = robot.get_observation().arm.get(GRIPPER)
        self.last_gripper = gripper
        if self.gripper_open_above is None or gripper is None:
            return True
        held = gripper > self.gripper_open_above  # a gripper that could not close is holding something
        log.info(
            "grasp check: gripper %s when the policy stopped, %.1f in the carry pose -> %s (threshold %.1f)",
            "?" if self.gripper_at_stop is None else f"{self.gripper_at_stop:.1f}",
            gripper, "holding" if held else "empty", self.gripper_open_above,
        )  # fmt: skip
        return held


class PickByCategory:
    """One pick skill per kind of object: the policy trained on socks for clothing, the one
    trained on cans for trash. An object of any other kind gets the default skill."""

    def __init__(self, skills: Mapping[Category, object], default):
        self.skills, self.default = dict(skills), default
        self.last_category: Category | None = None

    def run(self, robot: Robot, target: Target) -> bool:
        self.last_category = target.category
        return self.skills.get(target.category, self.default).run(robot, target)


def build_pick_skill(cfg: dict):
    m = cfg["manipulation"]
    poses = load_poses(CONFIG_DIR / m["poses_file"])
    pick = m["pick"]
    if pick["kind"] == "scripted":
        return ScriptedPick(ScriptedSequence(poses, pick["steps"], cfg["robot"]["fps"]))
    after = ScriptedSequence(poses, pick["after"], cfg["robot"]["fps"]) if pick.get("after") else None

    def policy(entry: Mapping) -> PolicyPick:
        return PolicyPick(
            pick["policy_type"],
            entry["policy_path"],
            entry.get("task", pick["task"]),
            entry.get("duration_s", pick["duration_s"]),
            cfg["robot"]["fps"],
            pick.get("device"),
            after,
            entry.get("gripper_open_above", pick.get("gripper_open_above")),
            entry.get("n_action_steps", pick.get("n_action_steps")),
        )

    # One policy per kind of object when `policies` lists them; `policy_path` is then the
    # one used for any other kind, if it is set.
    by_category = {Category(name): policy(entry) for name, entry in (pick.get("policies") or {}).items()}
    if not by_category:
        return policy(pick)
    default_set = pick.get("policy_path") and not str(pick["policy_path"]).startswith("CHANGE_ME")
    return PickByCategory(by_category, policy(pick) if default_set else next(iter(by_category.values())))


def build_drop_skill(cfg: dict) -> ScriptedDrop:
    m = cfg["manipulation"]
    poses = load_poses(CONFIG_DIR / m["poses_file"])
    return ScriptedDrop(
        {Category(c): ScriptedSequence(poses, steps, cfg["robot"]["fps"]) for c, steps in m["drop"].items()}
    )
