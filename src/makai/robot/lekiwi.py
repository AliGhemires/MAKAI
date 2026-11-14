"""Adapter between LeRobot's LeKiwi and the `makai.contracts.Robot` interface.

Two ways to reach the hardware, chosen by `robot.link` in the config:

- `host`: through the host on the Raspberry Pi (`LeKiwiClient`, ZMQ over WiFi): base, arm
  and cameras. The Pi must be running

      python -m lerobot.robots.lekiwi.lekiwi_host --robot.id=<robot.id> --host.connection_time_s=36000

- `wired`: `WiredBase` talks to the wheel servos over the motor board's USB cable, plugged
  into the machine running MAKAI: the Pi itself (/dev/ttyACM0), or a laptop (COM5). Base
  only. Needed while the arm is not mounted: LeRobot's LeKiwi, hence the host, refuses to
  start unless all nine motors answer.

The wheel values (motor IDs, port, radii, angles, speed cap) are in `robot.base`. In host
mode LeRobot on the Pi does the kinematics with its own built-in values, which are the same.

Facts checked against lerobot 0.7.0 (src/lerobot/robots/lekiwi and src/lerobot/motors,
unchanged in the 0.7.1 source install used on the robot):
- action / state keys: arm_<joint>.pos (degrees), x.vel and y.vel (m/s), theta.vel (deg/s);
- +x forward, +y left, +theta counter-clockwise: same as our base frame;
- the host needs all three *.vel keys in every command, arm keys are optional
  (joints that are not sent keep their last goal);
- the host stops the base by itself if it gets no command for 0.5 s (watchdog);
- wheels: STS3215 servos in velocity mode. Goal_Velocity and Present_Velocity are signed
  encoder steps per second (rustypot handles the sign bit), Present_Voltage is in 0.1 V.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from makai.contracts import BaseVelocity, Observation

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
ARM_KEYS = tuple(f"arm_{joint}.pos" for joint in ARM_JOINTS)
BASE_KEYS = ("x.vel", "y.vel", "theta.vel")
LINKS = ("host", "wired")
STEPS_PER_DEG = 4096 / 360


@dataclass(frozen=True)
class BaseGeometry:
    """The three omni wheels, from `robot.base` in configs/makai.yaml.

    Rim speed of wheel i = cos(a_i) * x + sin(a_i) * y + base_radius_m * theta (rad/s),
    the kinematics of LeRobot's LeKiwi.
    """

    motor_ids: Mapping[str, int]  # bus motor name -> servo ID, e.g. base_left_wheel -> 7
    angles_rad: tuple[float, ...]  # direction of each wheel in the base frame, same order
    wheel_radius_m: float
    base_radius_m: float
    max_wheel_raw: int  # steps/s; faster commands are scaled down, all wheels together

    @classmethod
    def from_config(cls, base: Mapping[str, Any]) -> BaseGeometry:
        wheels = list(base["motor_ids"])  # left, back, right
        return cls(
            motor_ids={f"base_{wheel}_wheel": int(base["motor_ids"][wheel]) for wheel in wheels},
            # LeRobot gives the angles as (240, 0, 120) and subtracts 90 degrees.
            angles_rad=tuple(math.radians(float(base["wheel_angles_deg"][wheel]) - 90.0) for wheel in wheels),
            wheel_radius_m=float(base["wheel_radius_m"]),
            base_radius_m=float(base["base_radius_m"]),
            max_wheel_raw=int(base["max_wheel_raw"]),
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.motor_ids)

    def _matrix(self) -> np.ndarray:
        return np.array([[math.cos(a), math.sin(a), self.base_radius_m] for a in self.angles_rad])

    def body_to_wheel_raw(self, x: float, y: float, theta_degps: float) -> dict[str, int]:
        """Base velocity in LeRobot units (m/s, m/s, deg/s) -> Goal_Velocity of each wheel.

        Same as LeRobot's `LeKiwi._body_to_wheel_raw`: if a wheel would exceed max_wheel_raw,
        all three are scaled down together, so the robot slows down but keeps its direction.
        """
        rim_m_s = self._matrix() @ np.array([x, y, math.radians(theta_degps)])
        raw = np.degrees(rim_m_s / self.wheel_radius_m) * STEPS_PER_DEG
        peak = float(np.abs(raw).max())
        if peak > self.max_wheel_raw:
            raw *= self.max_wheel_raw / peak
        return {name: round(float(value)) for name, value in zip(self.names, raw, strict=True)}

    def wheel_raw_to_body(self, raw: Mapping[str, float]) -> dict[str, float]:
        """Present_Velocity of each wheel -> base velocity in LeRobot units, keyed like the host's."""
        x, y, theta = self.wheel_steps_to_body(raw)
        return {"x.vel": x, "y.vel": y, "theta.vel": math.degrees(theta)}

    def wheel_steps_to_body(self, steps: Mapping[str, float]) -> tuple[float, float, float]:
        """Encoder steps of each wheel -> base motion (m, m, rad) in the base frame.

        Steps per second give a velocity, a step difference gives a displacement.
        """
        wheel = np.array([steps[name] for name in self.names], dtype=float)
        rim_m = np.radians(wheel / STEPS_PER_DEG) * self.wheel_radius_m
        x, y, theta = np.linalg.solve(self._matrix(), rim_m)
        return float(x), float(y), float(theta)


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


def make_wheel_bus(port: str, geometry: BaseGeometry):
    """LeRobot bus holding the three wheel servos only."""
    from lerobot.motors import Motor, MotorNormMode, SerialMotorsBus

    motors = {
        name: Motor(motor_id, "sts3215", MotorNormMode.RANGE_M100_100)
        for name, motor_id in geometry.motor_ids.items()
    }
    return SerialMotorsBus(port=port, motors=motors)


class WiredBase:
    """Stands in for `LeKiwiClient` when the motor board is plugged into this machine: base only.

    It takes and returns the client's x.vel / y.vel / theta.vel, so `LeKiwiRobot` works
    unchanged. Like the host, it stops the wheels when no command came for `watchdog_s`. It
    cannot stop them if the USB link itself drops, or if this process is killed: the servos
    then keep their last speed.
    """

    def __init__(self, bus, geometry: BaseGeometry, watchdog_s: float = 0.5):
        self.bus = bus
        self.geometry = geometry
        self.watchdog_s = watchdog_s
        self._lock = threading.Lock()  # the bus is shared with the watchdog thread
        self._moving = False
        self._last_command = 0.0
        self._closing = threading.Event()
        self._watchdog: threading.Thread | None = None

    def connect(self) -> None:
        self.bus.connect()  # fails unless every wheel servo answers
        self.bus.disable_torque()
        self.bus.set_operating_mode("velocity")  # written with the torque off
        self.bus.enable_torque()
        self._closing.clear()
        self._watchdog = threading.Thread(target=self._watch, name="wired-base-watchdog", daemon=True)
        self._watchdog.start()

    def disconnect(self) -> None:
        self._closing.set()
        if self._watchdog is not None:
            self._watchdog.join()
        try:
            with self._lock:
                self._write(0.0, 0.0, 0.0)
        finally:
            self.bus.disconnect()

    def send_action(self, action: Mapping[str, float]) -> None:
        with self._lock:
            self._write(*(float(action[key]) for key in BASE_KEYS))
        arm = sorted(key for key in action if key not in BASE_KEYS)
        if arm:
            raise RuntimeError(
                f"wired mode drives the base only, got arm keys {arm}: start the host on the Pi to use the arm"
            )

    def get_observation(self) -> dict[str, float]:
        with self._lock:
            raw = self.bus.sync_read("Present_Velocity", normalize=False)
        return self.geometry.wheel_raw_to_body(raw)

    def read_positions(self) -> dict[str, int]:
        """Encoder position of each wheel, 0 to 4095 steps per turn (it wraps around)."""
        with self._lock:
            return self.bus.sync_read("Present_Position", normalize=False)

    def read_voltage(self) -> float:
        """Battery voltage seen by the wheel servos, in volts."""
        with self._lock:
            raw = self.bus.sync_read("Present_Voltage", normalize=False)
        return sum(raw.values()) / len(raw) / 10.0

    def check_watchdog(self, now: float) -> bool:
        """Stop the wheels if the last motion command is older than `watchdog_s`. True if it did."""
        with self._lock:
            if not self._moving or now - self._last_command <= self.watchdog_s:
                return False
            self._write(0.0, 0.0, 0.0)
            return True

    def _watch(self) -> None:
        while not self._closing.wait(self.watchdog_s / 5):
            self.check_watchdog(time.monotonic())

    def _write(self, x: float, y: float, theta_degps: float) -> None:  # caller holds the lock
        goal = self.geometry.body_to_wheel_raw(x, y, theta_degps)
        self.bus.sync_write("Goal_Velocity", goal, normalize=False)
        self._moving = (x, y, theta_degps) != (0.0, 0.0, 0.0)
        self._last_command = time.monotonic()


class LeKiwiRobot:
    """Implements `makai.contracts.Robot` on the real LeKiwi."""

    def __init__(self, client, camera_names: tuple[str, ...] = ("front", "wrist")):
        self.client = client  # LeKiwiClient (or WiredBase), for policies that need it
        self.camera_names = camera_names
        self.raw_observation: dict[str, Any] = {}  # last LeRobot-format observation

    @classmethod
    def from_config(cls, cfg: dict, link: str | None = None) -> LeKiwiRobot:
        """`link` overrides `robot.link` from the config: "host" or "wired"."""
        robot = cfg["robot"]
        link = link or robot.get("link", "host")
        if link == "wired":  # base only: no host, no arm, no cameras
            geometry = BaseGeometry.from_config(robot["base"])
            bus = make_wheel_bus(robot["base"]["port"], geometry)
            return cls(WiredBase(bus, geometry, robot["base"].get("watchdog_s", 0.5)), camera_names=())
        if link == "host":
            return cls(make_client(cfg), tuple(robot["cameras"]))
        raise ValueError(f"robot.link must be one of {LINKS}, got {link!r}")

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

    def battery_voltage(self) -> float | None:
        """Battery voltage in volts, read from the wheel servos. None through the host."""
        read = getattr(self.client, "read_voltage", None)
        return read() if read is not None else None

    def wheel_positions(self) -> dict[str, int] | None:
        """Wheel encoder positions (wired mode). None through the host, which does not send them."""
        read = getattr(self.client, "read_positions", None)
        return read() if read is not None else None
