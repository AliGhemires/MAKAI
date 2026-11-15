"""A flight recorder for the base: what was commanded, what the servos said, what the wheels
really turned, and where the odometry put the robot. One line per observation while the base
moves, in data/odometry_trace_<time>.csv (not in git). Read it with scripts/odometry_report.py.

It answers, for any move, without a tape: did the speed readings and the encoders agree, did
the three wheels turn as much as each other, was the stream regular.
"""

from __future__ import annotations

import csv
import math
import time
from collections.abc import Mapping
from pathlib import Path

from makai.contracts import BaseVelocity

FIELDS = (
    "t",  # laptop clock, s
    "host_t",  # the Pi's clock, s (empty with a host that does not send it)
    "cmd_x",  # what was sent to the base: m/s, m/s, deg/s
    "cmd_y",
    "cmd_theta_deg",
    "speed_x",  # the servos' own speed readings, as LeRobot turns them into a base velocity
    "speed_y",
    "speed_theta_deg",
    "enc_left",  # wheel encoders, steps (empty with a host that does not send them)
    "enc_back",
    "enc_right",
    "odo_x",  # where the console's odometry puts the robot: m, m, deg
    "odo_y",
    "odo_yaw_deg",
)


class OdometryTrace:
    def __init__(self, path: Path, idle_s: float = 2.0):
        self.path, self.idle_s = path, idle_s
        self._file = None
        self._writer = None
        self._active_until = -math.inf
        self.rows = 0

    @classmethod
    def in_folder(cls, folder: Path) -> OdometryTrace:
        return cls(folder / f"odometry_trace_{time.strftime('%Y%m%d_%H%M%S')}.csv")

    def note(
        self,
        stamp: float,
        host_time: float | None,
        command: BaseVelocity,
        speed: BaseVelocity,
        encoders: Mapping[str, float] | None,
        pose: tuple[float, float, float],
    ) -> None:
        """One observation. Kept while the base is commanded to move, and `idle_s` after."""
        if not command.is_zero():
            self._active_until = stamp + self.idle_s
        if stamp > self._active_until:
            return
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = self.path.open("w", newline="")
            self._writer = csv.writer(self._file)
            self._writer.writerow(FIELDS)
        wheels = ["", "", ""] if encoders is None else [int(v) for v in list(encoders.values())[:3]]
        self._writer.writerow(
            [
                f"{stamp:.4f}",
                "" if host_time is None else f"{host_time:.4f}",
                f"{command.x:.4f}",
                f"{command.y:.4f}",
                f"{math.degrees(command.theta):.3f}",
                f"{speed.x:.5f}",
                f"{speed.y:.5f}",
                f"{math.degrees(speed.theta):.4f}",
                *wheels,
                f"{pose[0]:.4f}",
                f"{pose[1]:.4f}",
                f"{math.degrees(pose[2]):.3f}",
            ]
        )
        self.rows += 1
        if self.rows % 30 == 0:
            self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = self._writer = None
