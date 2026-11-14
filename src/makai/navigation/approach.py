"""Drive the holonomic base so that a floor point ends up at a fixed spot in the base frame.

This is what makes the manipulation policy easy: every grasp starts with the object
at the same place relative to the robot (the canonical pre-grasp pose), both when
collecting demonstrations and when running autonomously.

Two phases:
- far:  turn to face the point and drive forward (keeps it in the camera's view);
- near: stop turning and translate in x/y only (holonomic fine alignment).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from makai.contracts import BaseVelocity


@dataclass(frozen=True)
class ApproachConfig:
    goal_x_m: float = 0.22  # where the point must end up, ahead of the base centre
    goal_y_m: float = 0.0
    tol_x_m: float = 0.01
    tol_y_m: float = 0.01
    settle_ticks: int = 5  # consecutive in-tolerance ticks before declaring arrival
    near_radius_m: float = 0.15  # error below which we switch to pure translation
    k_lin: float = 1.2  # 1/s
    k_ang: float = 1.5  # 1/s
    max_lin: float = 0.15  # m/s
    max_ang: float = 0.8  # rad/s
    min_lin: float = 0.02  # m/s, below this the wheels do not move (stiction)


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


class ApproachController:
    def __init__(self, cfg: ApproachConfig | None = None):
        self.cfg = cfg or ApproachConfig()
        self._settled = 0

    def reset(self) -> None:
        self._settled = 0

    def step(self, x_m: float, y_m: float) -> tuple[BaseVelocity, bool]:
        """One control tick given the point's current position in the base frame.

        Returns the velocity to send and whether the robot has arrived (and is stopped).
        """
        c = self.cfg
        ex, ey = x_m - c.goal_x_m, y_m - c.goal_y_m

        if abs(ex) <= c.tol_x_m and abs(ey) <= c.tol_y_m:
            self._settled += 1
            return BaseVelocity(), self._settled >= c.settle_ticks
        self._settled = 0

        if math.hypot(ex, ey) > c.near_radius_m:
            bearing = math.atan2(y_m, x_m)
            # Slow down the forward motion while badly aligned.
            alignment = max(0.0, math.cos(bearing)) ** 2
            vx = _clamp(c.k_lin * ex, c.max_lin) * alignment
            return BaseVelocity(x=vx, y=0.0, theta=_clamp(c.k_ang * bearing, c.max_ang)), False

        vx, vy = _clamp(c.k_lin * ex, c.max_lin), _clamp(c.k_lin * ey, c.max_lin)
        speed = math.hypot(vx, vy)
        if 0.0 < speed < c.min_lin:
            vx, vy = vx * c.min_lin / speed, vy * c.min_lin / speed
        return BaseVelocity(x=vx, y=vy, theta=0.0), False
