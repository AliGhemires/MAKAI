"""Sweep a rectangular room in lanes, like a robot vacuum (a "snake", or boustrophedon, path).

The map frame is the frame of the odometry: its origin is where the robot starts, which the
team places in front of the bin, facing the room. x points into the room, y to the left.

    y ^        wall
      |  +----------------------------+
      |  |  <----------------------+  |
      |  |  +----------------------+  |   lanes, `lane_spacing_m` apart
  bin O--|->+---------------------->  |
      |  |                            |
      |  +----------------------------+--> x
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    """The floor to sweep, in the map frame. The walls are at x = 0 .. length, y = -width/2 .. +width/2."""

    length_m: float = 2.0
    width_m: float = 1.6
    margin_m: float = 0.30  # the centre of the robot keeps this far from the walls

    @property
    def x_range(self) -> tuple[float, float]:
        return self.margin_m, max(self.margin_m, self.length_m - self.margin_m)

    @property
    def y_range(self) -> tuple[float, float]:
        half = max(0.0, self.width_m / 2 - self.margin_m)
        return -half, half

    def contains(self, x: float, y: float, slack_m: float = 0.0) -> bool:
        """Is this point on the floor of the room (walls included, plus `slack_m`)?"""
        return -slack_m <= x <= self.length_m + slack_m and abs(y) <= self.width_m / 2 + slack_m


def snake_waypoints(room: Room, lane_spacing_m: float = 0.5) -> list[tuple[float, float]]:
    """The corners of the snake path: up one lane, across, down the next, and so on.

    Lanes run along x and are at most `lane_spacing_m` apart, evenly spread over the width.
    The path starts in the corner on the robot's right (y < 0), close to the origin.
    """
    (x0, x1), (y0, y1) = room.x_range, room.y_range
    lanes = max(1, math.ceil((y1 - y0) / lane_spacing_m - 1e-9)) + 1 if y1 > y0 else 1
    points: list[tuple[float, float]] = []
    for lane in range(lanes):
        y = y0 + lane * (y1 - y0) / (lanes - 1) if lanes > 1 else 0.0
        ends = [(round(x0, 3), round(y, 3)), (round(x1, 3), round(y, 3))]  # to the millimetre
        points.extend(ends if lane % 2 == 0 else ends[::-1])
    return points


def path_length_m(points: list[tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
