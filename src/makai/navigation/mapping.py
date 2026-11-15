"""The map the robot builds while it sweeps: where it has been, what the camera has covered,
and where it saw, picked and delivered objects.

There is no range sensor on the robot. The map is built from two things only: the odometry
(where the base is) and the front camera's footprint on the floor (what it can see from there).
A cell of the grid is "covered" once the camera has looked at it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from makai.navigation.coverage import Room


@dataclass
class MapObject:
    """Something seen on the floor, in the map frame."""

    id: int
    label: str
    category: str
    x: float
    y: float
    status: str = "seen"  # seen -> approaching -> picked -> delivered, or abandoned


@dataclass
class RoomMap:
    room: Room
    cell_m: float = 0.05
    hfov_deg: float = 55.0  # the front camera's horizontal field of view
    min_range_m: float = 0.15
    max_range_m: float = 1.5  # how far the detector is trusted to see a small object
    same_object_m: float = 0.25  # two sightings closer than this are the same object
    trail_step_m: float = 0.03
    objects: list[MapObject] = field(default_factory=list)
    trail: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.xs = np.arange(self.cell_m / 2, self.room.length_m, self.cell_m)
        self.ys = np.arange(-self.room.width_m / 2 + self.cell_m / 2, self.room.width_m / 2, self.cell_m)
        self._grid_x, self._grid_y = np.meshgrid(self.xs, self.ys)  # rows are y, columns are x
        self.covered = np.zeros(self._grid_x.shape, dtype=bool)
        self._next_id = 1

    # ------------------------------------------------------------------ updates
    def see_from(self, x: float, y: float, yaw: float) -> None:
        """Mark the floor the camera looks at from this pose, and extend the trail."""
        dx, dy = self._grid_x - x, self._grid_y - y
        distance = np.hypot(dx, dy)
        bearing = np.arctan2(dy, dx) - yaw
        bearing = (bearing + np.pi) % (2 * np.pi) - np.pi
        in_view = (distance >= self.min_range_m) & (distance <= self.max_range_m)
        self.covered |= in_view & (np.abs(bearing) <= math.radians(self.hfov_deg) / 2)
        if not self.trail or math.dist(self.trail[-1], (x, y)) >= self.trail_step_m:
            self.trail.append((round(x, 3), round(y, 3)))

    def note(self, label: str, category: str, x: float, y: float, status: str = "seen") -> MapObject:
        """Record a sighting: a new object, or a better position for one already known.

        A sighting next to an object that was just picked is that same object, seen a moment
        before the gripper closed on it: it must not come back as a new one.
        """
        known = self.nearest(x, y, self.same_object_m, ("seen", "approaching", "picked"))
        if known is None:
            known = MapObject(self._next_id, label, category, x, y, status)
            self._next_id += 1
            self.objects.append(known)
        elif known.status != "picked":
            known.x, known.y, known.label, known.category = x, y, label, category
            if status != "seen":
                known.status = status
        return known

    def nearest(self, x: float, y: float, within_m: float, statuses: tuple[str, ...]) -> MapObject | None:
        best = min(
            (o for o in self.objects if o.status in statuses),
            key=lambda o: math.hypot(o.x - x, o.y - y),
            default=None,
        )
        return best if best is not None and math.hypot(best.x - x, best.y - y) <= within_m else None

    # ------------------------------------------------------------------ reading
    @property
    def coverage(self) -> float:
        """Share of the room's floor the camera has looked at, 0 to 1."""
        return float(self.covered.mean()) if self.covered.size else 0.0

    def snapshot(self, max_trail: int = 400) -> dict:
        """Everything the interface draws, as plain data."""
        step = max(1, len(self.trail) // max_trail)
        return {
            "room": {
                "length_m": self.room.length_m,
                "width_m": self.room.width_m,
                "margin_m": self.room.margin_m,
            },
            "cell_m": self.cell_m,
            "covered": ["".join("1" if cell else "0" for cell in row) for row in self.covered],
            "coverage": round(self.coverage, 3),
            "trail": self.trail[::step] + self.trail[-1:],
            "objects": [vars(o) | {"x": round(o.x, 3), "y": round(o.y, 3)} for o in self.objects],
        }
