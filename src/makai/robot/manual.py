"""Manual driving of the base: smooth and safe velocity commands from a human.

`ManualDriver` turns stick positions (from the web page in `drive_server.py`) into base
velocities:
- acceleration limits, so the robot never jerks, whatever the input does;
- a dead man's switch: when the page goes quiet for `deadman_s`, the robot brakes to a stop;
- one driver at a time, so two open pages cannot fight over the wheels;
- an emergency stop that cuts the speed at once and stays latched until released.

`DriveLoop` runs it against any `Robot` (real, wired or simulated) at a fixed rate, and
keeps what the page displays: measured velocity, odometry, battery voltage, errors.
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
from makai.robot.lekiwi import BaseGeometry

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
    ):
        self.robot, self.driver, self.geometry = robot, driver, geometry
        self.period, self.telemetry_period, self.voltage_period = (
            1 / rate_hz,
            1 / telemetry_hz,
            voltage_period_s,
        )
        self.clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_telemetry = self._next_voltage = -math.inf
        self.odometry = Odometry()
        self.odometry_epoch = 0  # bumped on reset, so the page clears its trail
        self.commanded = BaseVelocity()
        self.measured: BaseVelocity | None = None
        self.voltage: float | None = None
        self.errors: dict[str, str] = {}

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
        velocity = self.driver.step(now)
        self._attempt("drive", lambda: self.robot.drive(velocity))
        with self._lock:
            self.commanded = velocity
        if now >= self._next_telemetry:
            self._next_telemetry = now + self.telemetry_period
            self._attempt("observation", self._observe)
        if now >= self._next_voltage and hasattr(self.robot, "battery_voltage"):
            self._next_voltage = now + self.voltage_period
            self._attempt("battery", self._read_voltage)

    def reset_odometry(self) -> None:
        with self._lock:
            self.odometry = Odometry()
            self.odometry_epoch += 1

    def snapshot(self) -> dict[str, Any]:
        """What the page shows, as JSON-ready values."""
        with self._lock:
            cmd, odo = self.commanded, self.odometry
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
                "battery_v": None if self.voltage is None else round(self.voltage, 2),
                "error": "; ".join(f"{what}: {message}" for what, message in self.errors.items()) or None,
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

    def _observe(self) -> None:
        obs = self.robot.get_observation()
        with self._lock:
            self.measured = obs.base_velocity
            self.odometry.update(obs.base_velocity, obs.stamp)

    def _read_voltage(self) -> None:
        voltage = self.robot.battery_voltage()
        with self._lock:
            self.voltage = voltage

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
