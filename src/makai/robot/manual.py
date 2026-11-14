"""Manual driving of the base: smooth and safe velocity commands from a human.

`ManualDriver` turns stick positions (from the web page in `drive_server.py`) into base
velocities:
- acceleration limits, so the robot never jerks, whatever the input does;
- a dead man's switch: when the page goes quiet for `deadman_s`, the robot brakes to a stop;
- one driver at a time, so two open pages cannot fight over the wheels;
- an emergency stop that cuts the speed at once and stays latched until released.

`DriveLoop` runs it against any `Robot` (real, wired or simulated) at a fixed rate, and
keeps what the page displays: measured velocity, odometry, battery voltage, errors. It also
runs precise moves (`moves.py`): while one runs, it drives the wheels instead of the sticks.
Odometry comes from the wheel encoders when the robot gives them (wired mode), otherwise
from the measured speed.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from typing import Any

from makai.contracts import BaseVelocity, Robot
from makai.navigation.odometry import Odometry
from makai.robot.cameras import CameraHub
from makai.robot.lekiwi import ARM_KEYS, BaseGeometry
from makai.robot.moves import (
    MOVE_NAMES,
    MoveSpec,
    MoveTuning,
    Pose,
    PreciseMove,
    TrialLog,
    WheelOdometry,
    in_start_frame,
    to_display,
)

log = logging.getLogger(__name__)

OWNER_TIMEOUT_S = 1.0  # a page silent for this long no longer blocks the others
Vel = tuple[float, float, float]  # x m/s, y m/s, theta rad/s
ZERO: Vel = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class DriveLimits:
    """`teleop.drive` in configs/makai.yaml."""

    max_lin_m_s: float = 0.25
    max_ang_deg_s: float = 90.0
    accel_m_s2: float = 0.5
    decel_m_s2: float = 1.2
    ang_accel_deg_s2: float = 240.0
    ang_decel_deg_s2: float = 480.0
    deadman_s: float = 0.4
    default_speed: float = 0.5

    @classmethod
    def from_config(cls, drive: Mapping[str, Any]) -> DriveLimits:
        known = {f.name for f in fields(cls)}
        return cls(**{key: float(value) for key, value in drive.items() if key in known})


def _clip(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def _finite(value: Any) -> float:
    """Anything from the network -> a finite float (NaN, inf, text and None become 0)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def ramp(current: Vel, target: Vel, limits: DriveLimits, dt: float) -> Vel:
    """Move `current` towards `target` within the acceleration limits.

    The translation moves in a straight line in velocity space, so a diagonal stays a
    diagonal while it speeds up. Slowing down or reversing uses the (stronger) braking limit.
    """
    cx, cy, cw = current
    tx, ty, tw = target

    braking = math.hypot(tx, ty) < math.hypot(cx, cy) or tx * cx + ty * cy < 0
    step = (limits.decel_m_s2 if braking else limits.accel_m_s2) * dt
    dx, dy = tx - cx, ty - cy
    gap = math.hypot(dx, dy)
    if gap <= step:
        cx, cy = tx, ty
    else:
        cx, cy = cx + dx / gap * step, cy + dy / gap * step

    braking = abs(tw) < abs(cw) or tw * cw < 0
    step = math.radians(limits.ang_decel_deg_s2 if braking else limits.ang_accel_deg_s2) * dt
    cw += _clip(tw - cw, -step, step)
    return cx, cy, cw


class ManualDriver:
    """Stick input from web pages -> smooth base velocity. Thread-safe."""

    def __init__(self, limits: DriveLimits):
        self.limits = limits
        self._lock = threading.Lock()
        self._target: Vel = ZERO
        self._current: Vel = ZERO
        self._owner: str | None = None
        self._owner_label = ""
        self._last_input = -math.inf
        self._last_step: float | None = None
        self._estop = False

    def command(
        self,
        client: str,
        x: Any,
        y: Any,
        turn: Any,
        speed: Any,
        now: float,
        takeover: bool = False,
        label: str = "",
    ) -> bool:
        """Stick input from one page. False if another page is driving (input ignored).

        x forward, y left, turn counter-clockwise: each in [-1, 1], (x, y) clipped to the unit
        disk. speed in [0, 1] scales the maxima. A page becomes the driver by moving a stick
        while nobody else is driving, or with `takeover`; it then stays the driver, sending
        zeros while idle, until another page takes over.
        """
        x, y, turn, speed = (_finite(v) for v in (x, y, turn, speed))
        norm = math.hypot(x, y)
        if norm > 1.0:
            x, y = x / norm, y / norm
        turn, speed = _clip(turn, -1.0, 1.0), _clip(speed, 0.0, 1.0)
        moving = (x, y, turn) != (0.0, 0.0, 0.0)
        with self._lock:
            if not (self._owner == client or takeover or (moving and not self._owner_active(now))):
                return False
            self._owner, self._owner_label, self._last_input = client, label[:40], now
            lin = self.limits.max_lin_m_s * speed
            ang = math.radians(self.limits.max_ang_deg_s) * speed
            self._target = (x * lin, y * lin, turn * ang)
            return True

    def emergency_stop(self) -> None:
        with self._lock:
            self._estop = True
            self._target = self._current = ZERO

    def release(self) -> None:
        """Clear the emergency stop. The robot stays still until the next stick input."""
        with self._lock:
            self._estop = False
            self._target = ZERO

    @property
    def estopped(self) -> bool:
        with self._lock:
            return self._estop

    def claim(self, client: str, now: float, label: str = "") -> bool:
        """Become the driver without moving a stick, to start a precise move. False if another page drives."""
        with self._lock:
            if self._owner != client and self._owner_active(now):
                return False
            self._owner, self._owner_label, self._last_input = client, label[:40], now
            return True

    def reset_motion(self) -> None:
        """Forget the current speed and stick target: a precise move takes or gives back the wheels."""
        with self._lock:
            self._target = self._current = ZERO
            self._last_step = None  # the next step must not see the whole move as one long tick

    def step(self, now: float) -> BaseVelocity:
        """Velocity to send now. Call it at a steady rate."""
        with self._lock:
            dt = 0.0 if self._last_step is None else _clip(now - self._last_step, 0.0, 0.1)
            self._last_step = now
            if self._estop:
                self._current = ZERO
            else:
                fresh = now - self._last_input <= self.limits.deadman_s
                self._current = ramp(self._current, self._target if fresh else ZERO, self.limits, dt)
            return BaseVelocity(*self._current)

    def status(self, client: str | None, now: float) -> dict[str, Any]:
        with self._lock:
            active = self._owner_active(now)
            return {
                "estop": self._estop,
                "you_drive": active and client is not None and self._owner == client,
                "driver": self._owner_label if active and self._owner != client else None,
            }

    def _owner_active(self, now: float) -> bool:  # caller holds the lock
        return self._owner is not None and now - self._last_input <= OWNER_TIMEOUT_S


def _velocity_dict(v: BaseVelocity) -> dict[str, float]:
    return {"x": round(v.x, 4), "y": round(v.y, 4), "theta_deg": round(math.degrees(v.theta), 2)}


def _move_dict(move: PreciseMove) -> dict[str, Any]:
    """A running move, in the page's units (cm or degrees), with its goal on the map."""
    axis, target = move.spec.axis, move.spec.target
    sign = math.copysign(1.0, target)
    x0, y0, yaw0 = move.start
    goal = None
    if axis != "theta":
        gx, gy = (target, 0.0) if axis == "x" else (0.0, target)
        goal = {
            "x": round(x0 + math.cos(yaw0) * gx - math.sin(yaw0) * gy, 4),
            "y": round(y0 + math.sin(yaw0) * gx + math.cos(yaw0) * gy, 4),
        }
    return {
        "move": MOVE_NAMES[(axis, int(sign))],
        "unit": "deg" if axis == "theta" else "cm",
        "target": round(abs(to_display(axis, target)), 2),
        "progress": round(sign * to_display(axis, move.progress), 2),
        "phase": move.phase,
        "goal": goal,
    }


class DriveLoop:
    """Owns the robot: at `rate_hz`, asks the driver for a velocity and sends it.

    All robot calls happen on this loop's thread. Errors (a USB cable pulled out...) are
    logged and shown on the page; the loop keeps trying, so it recovers if the link returns.
    """

    def __init__(
        self,
        robot: Robot,
        driver: ManualDriver,
        geometry: BaseGeometry | None = None,
        rate_hz: float = 50.0,
        telemetry_hz: float = 10.0,
        voltage_period_s: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        trials: TrialLog | None = None,
        truth: Callable[[], Pose] | None = None,
        cameras: CameraHub | None = None,
        tuning: MoveTuning | None = None,
    ):
        self.robot, self.driver, self.geometry = robot, driver, geometry
        self.period, self.telemetry_period, self.voltage_period = (
            1 / rate_hz,
            1 / telemetry_hz,
            voltage_period_s,
        )
        self.clock = clock
        self.trials = trials if trials is not None else TrialLog()
        self.truth = truth  # simulation only: where the robot really is
        self.cameras = cameras  # images from the observations go there (host mode)
        self.tuning = tuning or MoveTuning()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_telemetry = self._next_voltage = -math.inf
        self._encoders: bool | None = None  # does the robot give wheel encoders? found on the first tick
        self.odometry: Odometry | WheelOdometry = Odometry()
        self.odometry_epoch = 0  # bumped on reset, so the page clears its trail
        self.commanded = BaseVelocity()
        self.measured: BaseVelocity | None = None
        self.voltage: float | None = None
        self.temperatures: dict[str, int] | None = None
        self.arm: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self._move: PreciseMove | None = None
        self._cancel: str | None = None
        self.last_trial: dict[str, Any] | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="drive-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the loop, then the base."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self.robot.stop()

    def tick(self, now: float) -> None:
        if self._encoders is not False:
            self._attempt("encoders", self._read_encoders)
        if now >= self._next_telemetry:
            self._next_telemetry = now + self.telemetry_period
            self._attempt("observation", self._observe)
        velocity = self._next_velocity(now)
        self._attempt("drive", lambda: self.robot.drive(velocity))
        with self._lock:
            self.commanded = velocity
        if now >= self._next_voltage and hasattr(self.robot, "battery_voltage"):
            self._next_voltage = now + self.voltage_period
            self._attempt("battery", self._read_health)

    def reset_odometry(self) -> bool:
        """Start the path from here. Refused (False) during a precise move."""
        with self._lock:
            if self._move is not None:
                return False
            self.odometry = WheelOdometry(self.geometry) if self._encoders and self.geometry else Odometry()
            self.odometry_epoch += 1
            return True

    def start_move(self, client: str, spec: MoveSpec, now: float, label: str = "") -> None:
        """Start a precise move from where the robot is. ValueError, with the reason, if it cannot."""
        if self.driver.estopped:
            raise ValueError("Emergency stop is on: resume first.")
        with self._lock:
            if self._move is not None:
                raise ValueError("A move is already running.")
            if not self.commanded.is_zero():
                raise ValueError("The robot is still moving: let it stop first.")
        if not self.driver.claim(client, now, label):
            raise ValueError("Another device is driving: take over first.")
        self.driver.reset_motion()
        limits = self.driver.limits
        with self._lock:
            self._cancel = None
            self._move = PreciseMove(
                spec, self._pose(), now, self.tuning, limits.max_lin_m_s, limits.max_ang_deg_s
            )

    def cancel_move(self) -> None:
        with self._lock:
            if self._move is not None:
                self._cancel = "cancelled"

    def snapshot(self) -> dict[str, Any]:
        """What the page shows, as JSON-ready values."""
        with self._lock:
            cmd, odo, move = self.commanded, self.odometry, self._move
            wheels = None
            if self.geometry is not None:
                raw = self.geometry.body_to_wheel_raw(cmd.x, cmd.y, math.degrees(cmd.theta))
                wheels = {
                    name.removeprefix("base_").removesuffix("_wheel"): round(
                        value / self.geometry.max_wheel_raw, 3
                    )
                    for name, value in raw.items()
                }
            return {
                "cmd": _velocity_dict(cmd),
                "meas": _velocity_dict(self.measured) if self.measured is not None else None,
                "wheels": wheels,
                "pose": {
                    "x": round(odo.x, 4),
                    "y": round(odo.y, 4),
                    "yaw_deg": round(math.degrees(odo.yaw), 2),
                },
                "odometry_epoch": self.odometry_epoch,
                "odometry_source": {True: "wheel encoders", False: "measured speed"}.get(self._encoders),
                "battery_v": None if self.voltage is None else round(self.voltage, 2),
                "temperatures": self.temperatures,
                # Joint angles in degrees, gripper 0 (closed) to 100 (open); {} when unknown.
                "arm": {
                    key.removeprefix("arm_").removesuffix(".pos"): round(v, 1) for key, v in self.arm.items()
                },
                "cameras": self.cameras.status() if self.cameras is not None else {},
                "error": "; ".join(f"{what}: {message}" for what, message in self.errors.items()) or None,
                "move": None if move is None else _move_dict(move),
                "last_trial": self.last_trial,
                "trials_version": self.trials.version,
            }

    def _run(self) -> None:
        next_tick = self.clock()
        while not self._stop.is_set():
            self.tick(self.clock())
            next_tick += self.period
            delay = next_tick - self.clock()
            if delay < -self.period:  # fell behind (slow bus): do not try to catch up
                next_tick = self.clock()
            self._stop.wait(max(0.0, delay))

    def _pose(self) -> Pose:  # caller holds the lock
        return self.odometry.x, self.odometry.y, self.odometry.yaw

    def _read_encoders(self) -> None:
        read = getattr(self.robot, "wheel_positions", None)
        positions = read() if read is not None and self.geometry is not None else None
        with self._lock:
            if positions is None:
                self._encoders = False  # through the host, or simulated: odometry from the speed
                return
            if not self._encoders:
                self._encoders = True
                self.odometry = WheelOdometry(self.geometry)
            self.odometry.update(positions)

    def _observe(self) -> None:
        obs = self.robot.get_observation()
        if self.cameras is not None:
            for name, image in obs.images.items():
                self.cameras.put(name, image, rgb=True)  # LeRobot images are RGB
        with self._lock:
            self.measured = obs.base_velocity
            self.arm = {key: obs.arm[key] for key in ARM_KEYS if key in obs.arm}
            if not self._encoders:
                self.odometry.update(obs.base_velocity, obs.stamp)

    def _next_velocity(self, now: float) -> BaseVelocity:
        with self._lock:
            move, cancel, pose = self._move, self._cancel, self._pose()
            self._cancel = None
        if move is None:
            return self.driver.step(now)
        if move.truth_start is None and self.truth is not None:
            move.truth_start = self.truth()
        if self.driver.estopped:
            move.cancel("stopped", pose, now)
        elif cancel:
            move.cancel(cancel, pose, now)
        velocity = move.step(pose, now)
        if velocity is not None:
            return velocity
        self._finish_move(move)
        return BaseVelocity()

    def _finish_move(self, move: PreciseMove) -> None:
        truth = None
        if self.truth is not None and move.truth_start is not None:
            truth = dict(
                zip(("x", "y", "theta"), in_start_frame(move.truth_start, self.truth()), strict=True)
            )[move.spec.axis]
        trial = self.trials.add(move.result, self.geometry, truth)
        self.driver.reset_motion()  # the sticks start again from standstill
        with self._lock:
            self._move, self.last_trial = None, trial
        log.info(
            "move %d: %s %.2f %s, wheels %.2f (%s)",
            trial["id"],
            trial["move"],
            trial["target"],
            trial["unit"],
            trial["wheels"],
            trial["status"],
        )

    def _read_health(self) -> None:
        voltage = self.robot.battery_voltage()
        read_temperatures = getattr(self.robot, "motor_temperatures", None)
        temperatures = read_temperatures() if read_temperatures is not None else None
        with self._lock:
            self.voltage, self.temperatures = voltage, temperatures

    def _attempt(self, what: str, action: Callable[[], None]) -> None:
        try:
            action()
        except Exception as exc:  # keep driving the page: it shows the error, the loop retries
            message = f"{type(exc).__name__}: {exc}"
            with self._lock:
                first = self.errors.get(what) != message
                self.errors[what] = message
            if first:
                log.error("%s failed: %s", what, message)
        else:
            if what in self.errors:
                with self._lock:
                    self.errors.pop(what, None)
                log.info("%s works again", what)
