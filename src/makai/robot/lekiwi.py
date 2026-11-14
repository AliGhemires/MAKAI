"""Adapter between LeRobot's LeKiwi and the `makai.contracts.Robot` interface.

Two ways to reach the hardware, chosen by `robot.link` in the config:

- `host`: through the host on the Raspberry Pi (`LeKiwiClient`, ZMQ over WiFi): base, arm
  and cameras. The Pi must be running

      python -m lerobot.robots.lekiwi.lekiwi_host --robot.id=<robot.id> --host.connection_time_s=36000

- `wired`: `WiredBase` talks to the wheel servos over the motor board's USB cable, plugged
  into the machine running MAKAI: the Pi itself (/dev/ttyACM0), or a laptop (COM5). It
  drives the base, and only READS the arm (joint angles, with the arm calibration saved on
  that machine by `lerobot-calibrate`): it never writes to the arm servos, not even their
  torque. Works without the arm too.

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

import json
import logging
import math
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from makai.contracts import BaseVelocity, Observation

ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
ARM_KEYS = tuple(f"arm_{joint}.pos" for joint in ARM_JOINTS)
ARM_MOTOR_IDS = {f"arm_{joint}": motor_id for motor_id, joint in enumerate(ARM_JOINTS, start=1)}  # as LeKiwi
BASE_KEYS = ("x.vel", "y.vel", "theta.vel")
LINKS = ("host", "wired")
STEPS_PER_DEG = 4096 / 360
CURRENT_MA_PER_UNIT = 6.5  # STS3215 Present_Current
STATUS_BITS = {1: "voltage", 2: "angle sensor", 4: "overheat", 8: "overcurrent", 32: "overload"}
DETAIL_REGISTERS = (
    "Present_Position",
    "Present_Velocity",
    "Present_Load",
    "Present_Current",
    "Present_Voltage",
    "Present_Temperature",
    "Torque_Enable",
    "Status",
    "Moving",
)
log = logging.getLogger(__name__)


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


def arm_calibration_path(robot_id: str) -> Path | None:
    """The arm calibration to read the arm with: the one `lerobot-calibrate --robot.type=lekiwi`
    saved on this machine, else the copy of our robot's calibration kept in the repo
    (calibration/robots/lekiwi/). None if neither exists."""
    from makai.config import REPO_ROOT

    candidates = []
    try:
        from lerobot.utils.constants import HF_LEROBOT_CALIBRATION, ROBOTS

        candidates.append(HF_LEROBOT_CALIBRATION / ROBOTS / "lekiwi" / f"{robot_id}.json")
    except ImportError:
        pass
    candidates.append(REPO_ROOT / "calibration" / "robots" / "lekiwi" / f"{robot_id}.json")
    return next((path for path in candidates if path.is_file()), None)


def load_arm_calibration(path: Path | None) -> dict[str, Any] | None:
    """The six arm servos' calibration, or None when there is no complete calibration file."""
    if path is None or not path.is_file():
        return None
    from lerobot.motors import MotorCalibration

    data = json.loads(path.read_text())
    calibration = {name: MotorCalibration(**data[name]) for name in ARM_MOTOR_IDS if name in data}
    return calibration if len(calibration) == len(ARM_MOTOR_IDS) else None


def make_wheel_bus(port: str, geometry: BaseGeometry, arm_calibration: Mapping[str, Any] | None = None):
    """LeRobot bus holding the three wheel servos, plus the arm servos (to read) if calibrated."""
    from lerobot.motors import Motor, MotorNormMode, SerialMotorsBus

    motors = {
        name: Motor(motor_id, "sts3215", MotorNormMode.RANGE_M100_100)
        for name, motor_id in geometry.motor_ids.items()
    }
    if arm_calibration:  # same units as the host: degrees, gripper 0 (closed) to 100 (open)
        for name, motor_id in ARM_MOTOR_IDS.items():
            mode = MotorNormMode.RANGE_0_100 if name == "arm_gripper" else MotorNormMode.DEGREES
            motors[name] = Motor(motor_id, "sts3215", mode)
    return SerialMotorsBus(port=port, motors=motors, calibration=dict(arm_calibration or {}) or None)


class WiredBase:
    """Stands in for `LeKiwiClient` when the motor board is plugged into this machine.

    It takes and returns the client's x.vel / y.vel / theta.vel (plus the arm joint angles
    when the arm is on the bus), so `LeKiwiRobot` works unchanged. Only the wheels are ever
    written to: torque, mode and speed. Like the host, it stops the wheels when no command came
    for `watchdog_s`. It cannot stop them if the USB link itself drops, or if this process is
    killed: the servos then keep their last speed.
    """

    def __init__(self, bus, geometry: BaseGeometry, watchdog_s: float = 0.5, fallback_bus=None):
        self.bus = bus
        self.fallback_bus = fallback_bus  # wheels only: used if the arm servos do not answer
        self.calibration_file: Path | None = None  # the arm calibration in use, for the logs
        self.geometry = geometry
        self.watchdog_s = watchdog_s
        self._lock = threading.Lock()  # the bus is shared with the watchdog thread
        self._moving = False
        self._last_command = 0.0
        self._closing = threading.Event()
        self._watchdog: threading.Thread | None = None

    @property
    def wheels(self) -> list[str]:
        return list(self.geometry.names)

    @property
    def arm(self) -> list[str]:
        return [name for name in self.bus.motors if name not in self.geometry.motor_ids]

    def connect(self) -> None:
        try:
            self.bus.connect()  # only pings: fails unless every servo on this bus answers
        except RuntimeError as exc:
            if self.fallback_bus is None:
                raise
            log.warning("arm servos do not answer (%s): driving the wheels only", exc)
            self.bus, self.fallback_bus = self.fallback_bus, None
            self.bus.connect()
        wheels = self.wheels
        self.bus.disable_torque(wheels)
        self.bus.set_operating_mode("velocity", wheels)  # written with the torque off
        self.bus.enable_torque(wheels)
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
                self.bus.disable_torque(self.wheels)
        finally:
            self.bus.disconnect(disable_torque=False)  # the default would also release the arm

    def send_action(self, action: Mapping[str, float]) -> None:
        with self._lock:
            self._write(*(float(action[key]) for key in BASE_KEYS))
        arm = sorted(key for key in action if key not in BASE_KEYS)
        if arm:
            raise RuntimeError(
                f"wired mode drives the base only, got arm keys {arm}: start the host on the Pi to use the arm"
            )

    def get_observation(self) -> dict[str, float]:
        arm = self.arm
        with self._lock:
            raw = self.bus.sync_read("Present_Velocity", self.wheels, normalize=False)
            joints = self.bus.sync_read("Present_Position", arm) if arm else {}
        return {
            **self.geometry.wheel_raw_to_body(raw),
            **{f"{name}.pos": float(v) for name, v in joints.items()},
        }

    def read_positions(self) -> dict[str, int]:
        """Encoder position of each wheel, 0 to 4095 steps per turn (it wraps around)."""
        with self._lock:
            return self.bus.sync_read("Present_Position", self.wheels, normalize=False)

    def read_voltage(self) -> float:
        """Battery voltage seen by the wheel servos, in volts."""
        with self._lock:
            raw = self.bus.sync_read("Present_Voltage", self.wheels, normalize=False)
        return sum(raw.values()) / len(raw) / 10.0

    def read_motor_details(self) -> dict[str, dict[str, Any]]:
        """What every servo on the bus measures now, in physical units. Only reads."""
        with self._lock:
            raw = {register: self.bus.sync_read(register, normalize=False) for register in DETAIL_REGISTERS}
        details = {}
        for name, motor in self.bus.motors.items():
            status = int(raw["Status"][name])
            details[name] = {
                "id": motor.id,
                "position": int(raw["Present_Position"][name]),  # encoder steps, 0 to 4095 per turn
                "velocity": int(raw["Present_Velocity"][name]),  # steps/s
                "load_pct": round(raw["Present_Load"][name] / 10.0, 1),  # % of max torque, signed
                "current_ma": round(raw["Present_Current"][name] * CURRENT_MA_PER_UNIT),
                "voltage_v": round(raw["Present_Voltage"][name] / 10.0, 1),
                "temperature_c": int(raw["Present_Temperature"][name]),
                "torque": bool(raw["Torque_Enable"][name]),
                "moving": bool(raw["Moving"][name]),
                "errors": [text for bit, text in STATUS_BITS.items() if status & bit],
            }
        return details

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
        if link == "wired":  # no host: the wheels, the arm read-only, cameras opened by the caller
            geometry = BaseGeometry.from_config(robot["base"])
            port = robot["base"]["port"]
            calibration_file = arm_calibration_path(robot["id"])
            arm_calibration = load_arm_calibration(calibration_file)
            bus = make_wheel_bus(port, geometry, arm_calibration)
            fallback = make_wheel_bus(port, geometry) if arm_calibration else None
            base = WiredBase(bus, geometry, robot["base"].get("watchdog_s", 0.5), fallback_bus=fallback)
            base.calibration_file = calibration_file if arm_calibration else None
            return cls(base, camera_names=())
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

    def motor_details(self) -> dict[str, dict[str, Any]] | None:
        """Every servo's measurements: position, speed, load, current, voltage, temperature,
        torque, errors (wired mode). None through the host, which does not send them."""
        read = getattr(self.client, "read_motor_details", None)
        return read() if read is not None else None

    def wheel_positions(self) -> dict[str, int] | None:
        """Wheel encoder positions (wired mode). None through the host, which does not send them."""
        read = getattr(self.client, "read_positions", None)
        return read() if read is not None else None
