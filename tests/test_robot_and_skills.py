import math

import pytest

from makai.config import load_config
from makai.contracts import BaseVelocity, Category, Robot, Target
from makai.manipulation.skills import ScriptedDrop, ScriptedPick, ScriptedSequence, load_poses, move_to
from makai.robot.lekiwi import ARM_KEYS, LeKiwiRobot, from_lerobot_observation, to_lerobot_base
from makai.sim.world import SimRobot, SimWorld


class FakeClient:
    """Stands in for lerobot's LeKiwiClient."""

    def __init__(self):
        self.sent = []

    def connect(self): ...

    def disconnect(self): ...

    def get_observation(self):
        return {
            **{k: 10.0 for k in ARM_KEYS},
            "x.vel": 0.1,
            "y.vel": 0.0,
            "theta.vel": 90.0,
            "front": "image",
        }

    def send_action(self, action):
        self.sent.append(action)


def test_base_velocity_is_converted_to_lerobot_units():
    assert to_lerobot_base(BaseVelocity(0.1, -0.05, math.pi / 2)) == {
        "x.vel": 0.1,
        "y.vel": -0.05,
        "theta.vel": pytest.approx(90.0),
    }


def test_observation_is_converted_from_lerobot_units():
    obs = from_lerobot_observation(FakeClient().get_observation(), ("front", "wrist"), stamp=1.0)
    assert obs.base_velocity.theta == pytest.approx(math.pi / 2)
    assert set(obs.arm) == set(ARM_KEYS) and list(obs.images) == ["front"]


def test_lekiwi_robot_always_sends_the_three_base_keys():
    client = FakeClient()
    robot = LeKiwiRobot(client)
    assert isinstance(robot, Robot)
    robot.drive(BaseVelocity(x=0.1))
    robot.move_arm({"arm_gripper.pos": 50.0})
    robot.stop()
    assert all({"x.vel", "y.vel", "theta.vel"} <= set(action) for action in client.sent)
    assert client.sent[1]["arm_gripper.pos"] == 50.0 and client.sent[1]["x.vel"] == 0.0
    with pytest.raises(KeyError):
        robot.move_arm({"gripper": 1.0})


def test_move_to_reaches_the_pose_smoothly():
    robot = SimRobot(SimWorld())
    robot.arm = {"arm_gripper.pos": 0.0, "arm_elbow_flex.pos": 20.0}
    move_to(
        robot, {"arm_gripper.pos": 60.0, "arm_elbow_flex.pos": -10.0}, duration_s=1.0, sleep=lambda _: None
    )
    assert robot.arm == pytest.approx({"arm_gripper.pos": 60.0, "arm_elbow_flex.pos": -10.0})


def test_scripted_skills_play_their_poses():
    poses = {"a": {"arm_gripper.pos": 5.0}, "b": {"arm_gripper.pos": 80.0}}
    robot = SimRobot(SimWorld())
    sequence = ScriptedSequence(poses, ["a", ("b", 0.2)], sleep=lambda _: None)
    assert ScriptedPick(sequence).run(robot, Target(Category.TRASH, "can", 0.22, 0.0))
    assert robot.arm["arm_gripper.pos"] == pytest.approx(80.0)
    assert ScriptedDrop({Category.TRASH: sequence}).run(robot, Category.TRASH)
    with pytest.raises(KeyError):
        ScriptedSequence(poses, ["missing"])


def test_shared_config_is_consistent():
    cfg = load_config()
    poses = load_poses(
        __import__("makai.config", fromlist=["CONFIG_DIR"]).CONFIG_DIR / cfg["manipulation"]["poses_file"]
    )
    manipulation = cfg["manipulation"]
    used = [s if isinstance(s, str) else s[0] for steps in manipulation["drop"].values() for s in steps]
    used += [
        s if isinstance(s, str) else s[0]
        for s in manipulation["pick"]["steps"] + manipulation["pick"]["after"]
    ]
    assert set(used) <= set(poses), "every pose used in makai.yaml must exist in arm_poses.yaml"
    assert {Category(c) for c in cfg["perception"]["prompts"]} == {Category.CLOTHING, Category.TRASH}
    assert {Category(c) for c in cfg["perception"]["stations"]["marker_ids"].values()} == {
        Category.CLOTHING,
        Category.TRASH,
    }
    assert all(set(pose) == set(ARM_KEYS) for pose in poses.values())
