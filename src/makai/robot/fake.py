"""Stand-ins for the robot, the leader arm and the keyboard: rehearse a recording session
without any hardware (`scripts/record.py --dry-run`).

They subclass the real LeRobot classes, so LeRobot's own recording loop and dataset code run
unchanged. Only the hardware I/O is replaced.
"""

from __future__ import annotations

import math
import time

import numpy as np
from lerobot.robots.lekiwi import LeKiwiClient
from lerobot.teleoperators.keyboard import KeyboardTeleop
from lerobot.teleoperators.so_leader import SO101Leader
from lerobot.utils.constants import ACTION

JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")


class FakeKiwi(LeKiwiClient):
    """Returns moving test images and echoes back the last arm command as the arm state."""

    def __init__(self, config):
        super().__init__(config)
        self._fake_connected = False
        self._arm = {f"arm_{joint}.pos": 0.0 for joint in JOINTS}
        self._tick = 0

    @property
    def is_connected(self) -> bool:
        return self._fake_connected

    def connect(self) -> None:
        self._fake_connected = True

    def disconnect(self) -> None:
        self._fake_connected = False

    def get_observation(self) -> dict:
        self._tick += 1
        observation = {**self._arm, "x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
        for name, cam in self.config.cameras.items():
            image = np.full((cam.height, cam.width, 3), 90, dtype=np.uint8)
            x = (self._tick * 4) % max(1, cam.width - 60)
            image[cam.height // 2 : cam.height // 2 + 60, x : x + 60] = (220, 120, 40)
            observation[name] = image
        return observation

    def send_action(self, action: dict) -> dict:
        self._arm.update({key: float(value) for key, value in action.items() if key in self._arm})
        # Same return value as the real client: every state key, plus the vector.
        values = np.array([action.get(key, 0.0) for key in self._state_order], dtype=np.float32)
        sent = {key: values[i] for i, key in enumerate(self._state_order)}
        sent[ACTION] = values
        return sent


class FakeLeader(SO101Leader):
    """A leader arm that repeats a pick: rest at home, reach out, close, come back, rest."""

    CYCLE_S = 8.0  # 0-2 s at home, 2-4 s out, 4-6 s back with the gripper closed, 6-8 s at home

    def __init__(self, config):
        super().__init__(config)
        self._fake_connected = False
        self._start = time.perf_counter()

    @property
    def is_connected(self) -> bool:
        return self._fake_connected

    def connect(self, calibrate: bool = True) -> None:
        self._fake_connected = True

    def disconnect(self) -> None:
        self._fake_connected = False

    def get_action(self) -> dict:
        phase = (time.perf_counter() - self._start) % self.CYCLE_S
        reach = 0.0 if phase < 2 or phase >= 6 else math.sin(math.pi * (phase - 2) / 4)
        action = {
            f"{joint}.pos": 40.0 * reach * (1 if i % 2 == 0 else -1) for i, joint in enumerate(JOINTS[:5])
        }
        action["gripper.pos"] = 60.0 if phase < 4 else 5.0  # open on the way out, closed on the way back
        return action


class FakeKeyboard(KeyboardTeleop):
    """A keyboard nobody touches: the base stays still."""

    def __init__(self, config):
        super().__init__(config)
        self._fake_connected = False

    @property
    def is_connected(self) -> bool:
        return self._fake_connected

    def connect(self) -> None:
        self._fake_connected = True

    def disconnect(self) -> None:
        self._fake_connected = False

    def get_action(self) -> dict:
        return {}
