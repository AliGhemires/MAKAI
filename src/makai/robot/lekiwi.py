"""Adapter between LeRobot's `LeKiwiClient` and the `makai.contracts.Robot` interface.

The laptop talks to the Raspberry Pi over ZMQ; the Pi must be running the host:

    python -m lerobot.robots.lekiwi.lekiwi_host --robot.id=<robot.id> --host.connection_time_s=36000

Facts checked against lerobot 0.7.0 (src/lerobot/robots/lekiwi):
- action / state keys: arm_<joint>.pos (degrees), x.vel and y.vel (m/s), theta.vel (deg/s);
- +x forward, +y left, +theta counter-clockwise: same as our base frame;
- the host needs all three *.vel keys in every command, arm keys are optional
  (joints that are not sent keep their last goal);
- the host stops the base by itself if it gets no command for 0.5 s (watchdog).
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping
from typing import Any

from makai.contracts import BaseVelocity, Observation

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
ARM_KEYS = tuple(f"arm_{joint}.pos" for joint in ARM_JOINTS)
BASE_KEYS = ("x.vel", "y.vel", "theta.vel")


def to_lerobot_base(velocity: BaseVelocity) -> dict[str, float]:
    return {"x.vel": velocity.x, "y.vel": velocity.y, "theta.vel": math.degrees(velocity.theta)}


def from_lerobot_observation(
    raw: Mapping[str, Any], camera_names: tuple[str, ...], stamp: float
) -> Observation:
    return Observation(
        stamp=stamp,
        images={name: raw[name] for name in camera_names if raw.get(name) is not None},
        arm={key: float(raw[key]) for key in ARM_KEYS if key in raw},
        base_velocity=BaseVelocity(
            x=float(raw.get("x.vel", 0.0)),
            y=float(raw.get("y.vel", 0.0)),
            theta=math.radians(float(raw.get("theta.vel", 0.0))),
        ),
    )


def make_client(cfg: dict):
    """Build the LeRobot client from our config. Shared by the mission and the scripts."""
    from lerobot.cameras import Cv2Rotation
    from lerobot.cameras.opencv import OpenCVCameraConfig
    from lerobot.robots.lekiwi import LeKiwiClient, LeKiwiClientConfig

    cameras = {
        name: OpenCVCameraConfig(
            index_or_path=cam["index_or_path"],
            fps=cam.get("fps", cfg["robot"]["fps"]),
            width=cam["width"],
            height=cam["height"],
            rotation=Cv2Rotation(cam.get("rotation", 0)),
        )
        for name, cam in cfg["robot"]["cameras"].items()
    }
    return LeKiwiClient(
        LeKiwiClientConfig(remote_ip=cfg["robot"]["remote_ip"], id=cfg["robot"]["id"], cameras=cameras)
    )


class LeKiwiRobot:
    """Implements `makai.contracts.Robot` on the real LeKiwi."""

    def __init__(self, client, camera_names: tuple[str, ...] = ("front", "wrist")):
        self.client = client  # the raw LeRobot client, for policies that need it
        self.camera_names = camera_names
        self.raw_observation: dict[str, Any] = {}  # last LeRobot-format observation

    @classmethod
    def from_config(cls, cfg: dict) -> LeKiwiRobot:
        return cls(make_client(cfg), tuple(cfg["robot"]["cameras"]))

    def connect(self) -> None:
        self.client.connect()

    def disconnect(self) -> None:
        self.stop()
        self.client.disconnect()

    def get_observation(self) -> Observation:
        self.raw_observation = self.client.get_observation()
        return from_lerobot_observation(self.raw_observation, self.camera_names, time.monotonic())

    def drive(self, velocity: BaseVelocity) -> None:
        self.client.send_action(to_lerobot_base(velocity))

    def move_arm(self, joints: Mapping[str, float]) -> None:
        unknown = set(joints) - set(ARM_KEYS)
        if unknown:
            raise KeyError(f"unknown arm joints {sorted(unknown)}; expected keys like {ARM_KEYS[0]}")
        self.client.send_action({**joints, **to_lerobot_base(BaseVelocity())})

    def stop(self) -> None:
        self.client.send_action(to_lerobot_base(BaseVelocity()))
