"""Sweep a rectangular room like a robot vacuum.

The map frame is the frame of the odometry: its origin is where the robot starts, which the
team places in front of the bin, back to it, facing the room. x points into the room, y to
the left.

Rows (`row_waypoints`), the vacuum mode: the robot never turns. It keeps facing the room,
square to the wall behind it, slides sideways along a row, moves one row forward, slides back.
The camera always looks at the strip of floor it has not reached yet.

    y ^   wall behind the robot
      |  +----------------------------+
      |  |  ^------->v      ^------>  |
      |  |  |        |      |         |   rows, `lane_spacing_m` apart;
  bin O  |  |        |      |         |   the robot faces +x all along
      |  |  |        |      |         |
      |  +--^        v------>         +--> x
         start line (x = 0)

Lanes (`snake_waypoints`), the earlier path: the robot turns to follow lanes that run along x.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Room:
    """The floor to sweep, in the map frame: x = 0 .. length, y = y_offset -+ width/2.

    It may be a real room or an imaginary rectangle on the floor (`navigation.zone`)."""

    length_m: float = 2.0
    width_m: float = 1.6
    margin_m: float = 0.30  # the centre of the robot keeps this far from the edges (0 without walls)
    y_offset_m: float = 0.0  # centre of the zone, to the left of the start pose (0 = centred on it)

    @property
    def x_range(self) -> tuple[float, float]:
        return self.margin_m, max(self.margin_m, self.length_m - self.margin_m)

    @property
    def y_range(self) -> tuple[float, float]:
        half = max(0.0, self.width_m / 2 - self.margin_m)
        return self.y_offset_m - half, self.y_offset_m + half

    def contains(self, x: float, y: float, slack_m: float = 0.0) -> bool:
        """Is this point on the floor of the room (walls included, plus `slack_m`)?"""
        inside_y = abs(y - self.y_offset_m) <= self.width_m / 2 + slack_m
        return -slack_m <= x <= self.length_m + slack_m and inside_y


def snake_waypoints(room: Room, lane_spacing_m: float = 0.5) -> list[tuple[float, float]]:
    """The corners of the snake path: up one lane, across, down the next, and so on.

    Lanes run along x and are at most `lane_spacing_m` apart, evenly spread over the width.
    The path starts in the corner on the robot's right (y < 0), close to the origin.
    """
    (x0, x1), (y0, y1) = room.x_range, room.y_range
    lanes = max(1, math.ceil((y1 - y0) / lane_spacing_m - 1e-9)) + 1 if y1 > y0 else 1
    points: list[tuple[float, float]] = []
    for lane in range(lanes):
        y = y0 + lane * (y1 - y0) / (lanes - 1) if lanes > 1 else y0 + 0.0
        ends = [(round(x0, 3), round(y, 3)), (round(x1, 3), round(y, 3))]  # to the millimetre
        points.extend(ends if lane % 2 == 0 else ends[::-1])
    return points


def row_waypoints(room: Room, row_spacing_m: float = 0.5) -> list[tuple[float, float]]:
    """The corners of the path in rows: across the room, one row forward, back across.

    Rows run along y. The first one is the start line (x = 0): the robot is already on it, and
    every later row has been looked at from the row before, so the robot never slides over
    floor it has not seen. Rows are at most `row_spacing_m` apart; the last one leaves that
    much, at most, between itself and the far wall, and stays `margin_m` away from it.
    The path starts at the end of the start line on the robot's right (y < 0).
    """
    y0, y1 = room.y_range
    last = max(0.0, min(room.length_m - room.margin_m, room.length_m - row_spacing_m))
    rows = math.ceil(last / row_spacing_m - 1e-9) + 1 if last > 0 else 1
    points: list[tuple[float, float]] = []
    for row in range(rows):
        x = round(row * last / (rows - 1), 3) if rows > 1 else 0.0
        ends = [(x, round(y0, 3)), (x, round(y1, 3))]
        for point in ends if row % 2 == 0 else ends[::-1]:
            if not points or points[-1] != point:  # a room one row wide: no sideways leg
                points.append(point)
    return points


def scan_waypoints(room: Room, swath_m: float = 1.6) -> list[tuple[float, float]]:
    """Wide lanes for a robot that looks left and right as it drives: one lane down the middle
    of every strip of floor at most `swath_m` wide.

    Lanes run along x, from the start line to 30 cm (or the margin) before the far edge: from
    there the camera sees the rest. The first lane is the one on the robot's right.
    """
    low = room.y_offset_m - room.width_m / 2
    lanes = max(1, math.ceil(room.width_m / swath_m - 1e-9))
    far = round(max(0.0, room.length_m - max(room.margin_m, 0.3)), 3)
    points: list[tuple[float, float]] = []
    for lane in range(lanes):
        y = round(low + (lane + 0.5) * room.width_m / lanes, 3)
        ends = [(0.0, y), (far, y)]
        points.extend(ends if lane % 2 == 0 else ends[::-1])
    return points


def path_length_m(points: list[tuple[float, float]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(points, points[1:], strict=False))
