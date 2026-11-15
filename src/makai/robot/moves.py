"""Precise moves: drive a set distance or angle, then compare with a tape measure.

- `WheelOdometry`: pose from the wheel encoders (wired mode). It counts the exact wheel
  turns, so unlike integrating the measured speed it does not depend on the loop rate.
- `PreciseMove`: go forward, back, left or right a set distance, or turn a set angle,
  closed loop on odometry. Gentle start, slows down before the end, stops when the target
  is reached (it never backs up, so an overshoot shows in the result), holds the two other
  axes on the way.
- `TrialLog`: every move with what the wheels measured, plus what the tape says once typed
  in. Statistics and suggested calibration of `robot.base.wheel_radius_m` (straight moves)
  and `robot.base.base_radius_m` (turns). Saved as CSV in data/ (not in git).

The wheels only know how much they turned, not how far the robot went: slip and a wrong
wheel radius are invisible to them. That is why moves are checked against a tape.
"""

from __future__ import annotations

import csv
import math
import shutil
import statistics
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from makai.contracts import BaseVelocity
from makai.robot.lekiwi import BaseGeometry

STEPS_PER_TURN = 4096
AXES = ("x", "y", "theta")  # forward(+)/back(-), left(+)/right(-), counter-clockwise(+)/clockwise(-)
MAX_DISTANCE_M = 3.0
MAX_ANGLE_RAD = math.radians(720)
Pose = tuple[float, float, float]  # x m, y m, yaw rad (not wrapped: counts full turns)


def wrap_steps(delta: float) -> float:
    """Encoder difference across the 4095 -> 0 wrap. Valid below half a turn between reads."""
    return (delta + STEPS_PER_TURN / 2) % STEPS_PER_TURN - STEPS_PER_TURN / 2


class WheelOdometry:
    """Pose of the base from its wheel encoders, in the frame it had at the first update."""

    def __init__(self, geometry: BaseGeometry):
        self.geometry = geometry
        self.x = self.y = self.yaw = 0.0
        self._last: dict[str, float] | None = None

    def update(self, positions: Mapping[str, float]) -> None:
        if self._last is not None:
            delta = {name: wrap_steps(positions[name] - self._last[name]) for name in self.geometry.names}
            dx, dy, dyaw = self.geometry.wheel_steps_to_body(delta)
            mid = self.yaw + dyaw / 2  # heading halfway through the step
            c, s = math.cos(mid), math.sin(mid)
            self.x += c * dx - s * dy
            self.y += s * dx + c * dy
            self.yaw += dyaw
        self._last = {name: float(positions[name]) for name in self.geometry.names}


@dataclass(frozen=True)
class MoveSpec:
    axis: str  # "x", "y" or "theta"
    target: float  # signed: m, or rad for theta
    speed: float  # cruise speed: m/s, or rad/s for theta

    def __post_init__(self) -> None:
        if self.axis not in AXES:
            raise ValueError(f"axis must be one of {AXES}, got {self.axis!r}")
        if not (math.isfinite(self.target) and math.isfinite(self.speed)):
            raise ValueError("target and speed must be numbers")
        limit = MAX_ANGLE_RAD if self.axis == "theta" else MAX_DISTANCE_M
        if not 0 < abs(self.target) <= limit:
            raise ValueError(
                f"target must be non-zero and at most {limit:g} ({'rad' if self.axis == 'theta' else 'm'})"
            )
        if self.speed <= 0:
            raise ValueError("speed must be positive")


@dataclass(frozen=True)
class MoveTuning:
    """How precise moves drive. Gentle on purpose: less slip, so the tape agrees with the wheels."""

    accel_m_s2: float = 0.3
    brake_m_s2: float = 0.25  # planned braking: starts slowing down early enough to stop on target
    creep_m_s: float = 0.012  # slowest speed near the end; the servos stall well below
    tol_m: float = 0.0003  # an encoder step is about 0.1 mm of travel
    ang_accel_deg_s2: float = 120.0
    ang_brake_deg_s2: float = 90.0
    creep_deg_s: float = 3.0
    tol_deg: float = 0.1
    hold_gain: float = 2.0  # 1/s: how hard the two other axes are pulled back to zero
    hold_max_m_s: float = 0.03
    hold_max_deg_s: float = 15.0
    settle_s: float = 0.5  # wait still before reading the result: the servos coast a little


def _clip(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def in_start_frame(start: Pose, pose: Pose) -> Pose:
    """`pose` relative to `start`: forward and left of where the robot was, and turned angle."""
    dx, dy = pose[0] - start[0], pose[1] - start[1]
    c, s = math.cos(start[2]), math.sin(start[2])
    return c * dx + s * dy, -s * dx + c * dy, pose[2] - start[2]


class PreciseMove:
    """One move. Call `step` at the control rate until it returns None, then read `result`."""

    def __init__(
        self,
        spec: MoveSpec,
        start: Pose,
        now: float,
        tuning: MoveTuning = MoveTuning(),
        max_lin_m_s: float = 0.25,
        max_ang_deg_s: float = 90.0,
    ):
        self.spec, self.start, self.tuning = spec, start, tuning
        self.angular = spec.axis == "theta"
        cap = math.radians(max_ang_deg_s) if self.angular else max_lin_m_s
        self.cruise = min(spec.speed, cap)
        if self.angular:
            self.accel = math.radians(tuning.ang_accel_deg_s2)
            self.brake = math.radians(tuning.ang_brake_deg_s2)
            self.creep = min(math.radians(tuning.creep_deg_s), self.cruise)
            self.tol = math.radians(tuning.tol_deg)
        else:
            self.accel, self.brake = tuning.accel_m_s2, tuning.brake_m_s2
            self.creep, self.tol = min(tuning.creep_m_s, self.cruise), tuning.tol_m
        expected = abs(spec.target) / self.cruise + self.cruise / self.accel + self.cruise / self.brake
        self.deadline = now + 2 * expected + 5.0
        self.started = now
        self.phase = "moving"  # -> settling -> done
        self.status = ""  # done | cancelled | stopped | timeout
        self.progress = 0.0
        self.truth_start: Pose | None = None
        self.result: dict[str, Any] | None = None
        self._speed = 0.0
        self._last_t = now
        self._settle_until = 0.0

    def step(self, pose: Pose, now: float) -> BaseVelocity | None:
        dt = max(0.0, min(0.1, now - self._last_t))
        self._last_t = now
        along_x, along_y, turned = in_start_frame(self.start, pose)
        self.progress = {"x": along_x, "y": along_y, "theta": turned}[self.spec.axis]
        if self.phase == "done":
            return None
        if self.phase == "settling":
            if now >= self._settle_until:
                self._finish("done", pose, now)
                return None
            return BaseVelocity()
        if now > self.deadline:
            self._finish("timeout", pose, now)
            return None

        direction = math.copysign(1.0, self.spec.target)
        remaining = direction * (self.spec.target - self.progress)  # > 0 until the target is reached
        if remaining <= self.tol:  # reached or passed: stop, never back up
            self.phase, self._speed = "settling", 0.0
            self._settle_until = now + self.tuning.settle_s
            return BaseVelocity()
        speed = min(self.cruise, math.sqrt(2 * self.brake * remaining), self._speed + self.accel * dt)
        self._speed = max(speed, self.creep)
        v = direction * self._speed

        k, hold_lin, hold_ang = (
            self.tuning.hold_gain,
            self.tuning.hold_max_m_s,
            math.radians(self.tuning.hold_max_deg_s),
        )
        if self.angular:  # turn on the spot: hold the position
            frame_x, frame_y, omega = _clip(-k * along_x, hold_lin), _clip(-k * along_y, hold_lin), v
        elif self.spec.axis == "x":  # forward/back: hold the side position and the heading
            frame_x, frame_y, omega = v, _clip(-k * along_y, hold_lin), _clip(-k * turned, hold_ang)
        else:  # left/right: hold the forward position and the heading
            frame_x, frame_y, omega = _clip(-k * along_x, hold_lin), v, _clip(-k * turned, hold_ang)
        # The commands above are in the start frame; the robot has turned by `turned` since.
        c, s = math.cos(turned), math.sin(turned)
        return BaseVelocity(x=c * frame_x + s * frame_y, y=-s * frame_x + c * frame_y, theta=omega)

    def cancel(self, status: str, pose: Pose, now: float) -> None:
        if self.phase != "done":
            self._finish(status, pose, now)

    def _finish(self, status: str, pose: Pose, now: float) -> None:
        along_x, along_y, turned = in_start_frame(self.start, pose)
        axis = self.spec.axis
        self.phase, self.status = "done", status
        self.result = {
            "axis": axis,
            "target": self.spec.target,
            "speed": self.cruise,
            "wheels": {"x": along_x, "y": along_y, "theta": turned}[axis],
            # Drift on the axes that should not have moved.
            "off_axis_m": math.hypot(along_x, along_y)
            if axis == "theta"
            else abs(along_y if axis == "x" else along_x),
            "heading_drift_rad": 0.0 if axis == "theta" else turned,
            "duration_s": now - self.started,
            "status": status,
        }


# ---- Trial log ---------------------------------------------------------------------------------

FIELDS = (
    "id",
    "time",
    "move",
    "unit",
    "target",
    "speed",
    "wheels",
    "tape",
    "sim_truth",
    "off_axis_cm",
    "heading_drift_deg",
    "duration_s",
    "status",
    "wheel_radius_m",
    "base_radius_m",
)


def wrap_angle(angle: float) -> float:
    """The same angle in [-pi, pi): the shortest way to turn."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


@dataclass(frozen=True)
class GoToTuning:
    """How the base drives back to a saved pose. Gentle, like the precise moves: less slip."""

    max_lin_m_s: float = 0.15
    max_ang_rad_s: float = 0.6
    accel_m_s2: float = 0.3  # gentle start
    gain_lin: float = 1.2  # 1/s: near the end, speed = gain x distance left
    gain_ang: float = 1.5
    creep_m_s: float = 0.015  # slowest useful speed; the servos stall well below
    creep_rad_s: float = 0.05
    tol_m: float = 0.01
    tol_rad: float = math.radians(1.5)
    settle_s: float = 0.4  # within tolerance this long before declaring arrival


class GoTo:
    """Drive back to a saved pose (x, y, yaw) on odometry. The base is omnidirectional: it
    goes straight there while turning to the saved heading, slows down near the end and holds
    still a moment. Call `step` at the control rate until it returns None, then read `status`
    (done, cancelled, stopped, timeout) and `error` (what odometry says is left)."""

    def __init__(self, name: str, goal: Pose, start: Pose, now: float, tuning: GoToTuning = GoToTuning()):
        self.name, self.goal, self.tuning = name, goal, tuning
        distance = math.hypot(goal[0] - start[0], goal[1] - start[1])
        turn = abs(wrap_angle(goal[2] - start[2]))
        self.deadline = now + 10.0 + 3 * distance / tuning.max_lin_m_s + 3 * turn / tuning.max_ang_rad_s
        self.phase, self.status = "moving", ""
        self.error: tuple[float, float] = (distance, turn)  # metres, radians: what is left
        self._speed, self._last_t, self._settle_until = 0.0, now, None

    def cancel(self, status: str) -> None:
        self.status = self.status or status

    def step(self, pose: Pose, now: float) -> BaseVelocity | None:
        t = self.tuning
        dt, self._last_t = max(0.0, now - self._last_t), now
        x, y, yaw = pose
        dx, dy = self.goal[0] - x, self.goal[1] - y
        distance, turn = math.hypot(dx, dy), wrap_angle(self.goal[2] - yaw)
        self.error = (distance, turn)
        if self.status:
            return None
        if now > self.deadline:
            self.status = "timeout"
            return None
        if distance <= t.tol_m and abs(turn) <= t.tol_rad:
            if self._settle_until is None:
                self.phase, self._settle_until = "settling", now + t.settle_s
            if now >= self._settle_until:
                self.status = "done"
                return None
            return BaseVelocity()
        self.phase, self._settle_until = "moving", None
        vx = vy = 0.0
        if distance > t.tol_m:
            wanted = max(t.creep_m_s, min(t.max_lin_m_s, t.gain_lin * distance))
            self._speed = min(wanted, self._speed + t.accel_m_s2 * dt)
            # The way to the goal, seen from the robot: it turns while it drives.
            ahead = math.cos(yaw) * dx + math.sin(yaw) * dy
            left = -math.sin(yaw) * dx + math.cos(yaw) * dy
            vx, vy = ahead / distance * self._speed, left / distance * self._speed
        w = 0.0
        if abs(turn) > t.tol_rad:
            w = math.copysign(max(t.creep_rad_s, min(t.max_ang_rad_s, t.gain_ang * abs(turn))), turn)
        return BaseVelocity(vx, vy, w)


MOVE_NAMES = {
    ("x", 1): "forward",
    ("x", -1): "back",
    ("y", 1): "left",
    ("y", -1): "right",
    ("theta", 1): "turn left",
    ("theta", -1): "turn right",
}
GROUPS = {"x": "forward / back", "y": "left / right", "theta": "turns"}


def _number(row: Mapping[str, str], key: str) -> float | None:
    return float(row[key]) if row.get(key) not in (None, "") else None


def to_display(axis: str, value: float) -> float:
    """m -> cm, rad -> degrees: the units of a tape measure and a protractor."""
    return math.degrees(value) if axis == "theta" else value * 100.0


class TrialLog:
    """Moves and their tape measurements, in display units (cm or degrees, as magnitudes)."""

    def __init__(self, path: Path | None = None):
        self.path = path
        self._lock = threading.Lock()
        self.trials: list[dict[str, Any]] = []
        self.version = 0
        if path is not None and path.exists():
            self._load(path)
        self._last_id = max((t["id"] for t in self.trials), default=0)  # never reused, even after clear

    def add(
        self, result: Mapping[str, Any], geometry: BaseGeometry | None, truth: float | None = None
    ) -> dict[str, Any]:
        axis = result["axis"]
        trial = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "move": MOVE_NAMES[(axis, 1 if result["target"] > 0 else -1)],
            "axis": axis,
            "unit": "deg" if axis == "theta" else "cm",
            "target": round(abs(to_display(axis, result["target"])), 2),
            "speed": round(to_display(axis, result["speed"]), 2),
            # Signed along the move: negative would mean it went the wrong way.
            "wheels": round(math.copysign(1, result["target"]) * to_display(axis, result["wheels"]), 2),
            "tape": None,
            "sim_truth": None
            if truth is None
            else round(math.copysign(1, result["target"]) * to_display(axis, truth), 2),
            "off_axis_cm": round(result["off_axis_m"] * 100, 2),
            "heading_drift_deg": round(math.degrees(result["heading_drift_rad"]), 2),
            "duration_s": round(result["duration_s"], 2),
            "status": result["status"],
            "wheel_radius_m": geometry.wheel_radius_m if geometry else None,
            "base_radius_m": geometry.base_radius_m if geometry else None,
        }
        with self._lock:
            self._last_id += 1
            trial["id"] = self._last_id
            self.trials.append(trial)
            self._changed()
        return trial

    def measure(self, trial_id: int, tape: float | None) -> dict[str, Any]:
        """Record what the tape (or protractor) says, as a positive number. None clears it."""
        if tape is not None and not (math.isfinite(tape) and 0 <= tape < 1000):
            raise ValueError("the measurement must be a positive number (cm, or degrees for turns)")
        with self._lock:
            trial = next((t for t in self.trials if t["id"] == trial_id), None)
            if trial is None:
                raise KeyError(trial_id)
            trial["tape"] = None if tape is None else round(tape, 2)
            self._changed()
            return dict(trial)

    def clear(self) -> None:
        with self._lock:
            if self.path is not None and self.path.exists() and self.trials:
                shutil.copy(
                    self.path, self.path.with_name(f"{self.path.stem}_{time.strftime('%Y%m%d_%H%M%S')}.csv")
                )
            self.trials = []
            self._changed()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"version": self.version, "trials": [dict(t) for t in self.trials], "stats": self._stats()}

    def csv_text(self) -> str:
        with self._lock:
            return self._csv()

    # Internals (caller holds the lock) -----------------------------------------------------------

    def _stats(self) -> dict[str, Any]:
        out = {}
        for axis, label in GROUPS.items():
            done = [t for t in self.trials if t["axis"] == axis and t["status"] == "done"]
            if not done:
                continue
            group: dict[str, Any] = {
                "label": label,
                "unit": "deg" if axis == "theta" else "cm",
                "moves": len(done),
            }
            wheel_err = [t["wheels"] - t["target"] for t in done]
            group["wheels_error_mean"] = round(statistics.fmean(wheel_err), 3)
            group["wheels_error_max"] = round(max(wheel_err, key=abs), 3)
            measured = [t for t in done if t["tape"] is not None and t["wheels"] > 0]
            group["measured"] = len(measured)
            if measured:
                tape_err = [t["tape"] - t["target"] for t in measured]
                group["tape_error_mean"] = round(statistics.fmean(tape_err), 3)
                group["tape_error_std"] = round(statistics.stdev(tape_err), 3) if len(tape_err) > 1 else None
                group["tape_error_max"] = round(max(tape_err, key=abs), 3)
                ratios = [t["tape"] / t["wheels"] for t in measured]
                group["tape_over_wheels"] = round(statistics.fmean(ratios), 4)
                if len(measured) >= 3:
                    group["suggestion"] = self._suggest(axis, measured)
            out[axis] = group
        return out

    @staticmethod
    def _suggest(axis: str, measured: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Calibration that would make the wheels agree with the tape, from each trial's own setting."""
        if axis == "theta":
            # Turned angle = rim travel / base radius: the robot turned less than the wheels
            # think if the real base radius is larger.
            values = [
                t["base_radius_m"] * t["wheels"] / t["tape"]
                for t in measured
                if t["base_radius_m"] and t["tape"]
            ]
            key, current = "base_radius_m", measured[-1]["base_radius_m"]
        else:
            # Travel = wheel turns x wheel radius.
            values = [t["wheel_radius_m"] * t["tape"] / t["wheels"] for t in measured if t["wheel_radius_m"]]
            key, current = "wheel_radius_m", measured[-1]["wheel_radius_m"]
        if not values or not current:
            return None
        value = statistics.fmean(values)
        return {
            "key": key,
            "current": current,
            "value": round(value, 5),
            "change_pct": round((value / current - 1) * 100, 2),
        }

    def _changed(self) -> None:
        self.version += 1
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(self._csv(), encoding="utf-8", newline="")

    def _csv(self) -> str:
        import io

        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for trial in self.trials:
            writer.writerow({k: ("" if trial.get(k) is None else trial.get(k)) for k in FIELDS})
        return buffer.getvalue()

    def _load(self, path: Path) -> None:
        names = {v: k for k, v in MOVE_NAMES.items()}
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                try:
                    axis = names[row["move"]][0]
                    number = partial(_number, row)
                    self.trials.append(
                        {
                            "id": int(row["id"]),
                            "time": row["time"],
                            "move": row["move"],
                            "axis": axis,
                            "unit": row["unit"],
                            **{
                                key: number(key) for key in ("target", "speed", "wheels", "tape", "sim_truth")
                            },
                            **{
                                key: number(key) for key in ("off_axis_cm", "heading_drift_deg", "duration_s")
                            },
                            "status": row["status"],
                            "wheel_radius_m": number("wheel_radius_m"),
                            "base_radius_m": number("base_radius_m"),
                        }
                    )
                except (KeyError, ValueError):
                    continue  # a hand-edited line we cannot read: skip it, keep the rest
