"""Shared data contracts between workstreams.

THIS FILE IS THE INTERFACE BETWEEN ALL MODULES. Changing it affects everyone:
say so in the team chat when you do, so nobody is surprised.

Conventions (see docs/ARCHITECTURE.md):
- Base frame: origin at the centre of the mobile base, on the floor.
  x = forward (m), y = left (m), angles counter-clockwise (rad).
- Images: HxWx3 uint8, RGB.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

import numpy as np


class Category(StrEnum):
    """What an object on the floor is, i.e. which station it must go to."""

    CLOTHING = "clothing"
    TRASH = "trash"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Detection:
    """A 2D detection in a camera image (pixels)."""

    label: str
    category: Category
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]

    @property
    def ground_pixel(self) -> tuple[float, float]:
        """Bottom-centre of the box: where the object touches the floor."""
        x1, _, x2, y2 = self.bbox_xyxy
        return ((x1 + x2) / 2.0, y2)


@dataclass(frozen=True)
class Target:
    """An object on the floor, located in the base frame (metres)."""

    category: Category
    label: str
    x_m: float
    y_m: float
    confidence: float = 1.0  # 0.0 = the category is only a guess (too far to classify yet)

    @property
    def distance_m(self) -> float:
        return math.hypot(self.x_m, self.y_m)

    @property
    def bearing_rad(self) -> float:
        return math.atan2(self.y_m, self.x_m)


@dataclass(frozen=True)
class StationSighting:
    """A drop-off station (bin or laundry basket) seen in the base frame."""

    category: Category  # the kind of object this station accepts
    x_m: float
    y_m: float

    @property
    def distance_m(self) -> float:
        return math.hypot(self.x_m, self.y_m)


@dataclass(frozen=True)
class Scene:
    """Everything perception extracted from one observation."""

    targets: tuple[Target, ...] = ()
    stations: Mapping[Category, StationSighting] = field(default_factory=dict)


@dataclass(frozen=True)
class BaseVelocity:
    """Holonomic base command in the base frame."""

    x: float = 0.0  # m/s, forward
    y: float = 0.0  # m/s, left
    theta: float = 0.0  # rad/s, counter-clockwise

    def is_zero(self) -> bool:
        return self.x == 0.0 and self.y == 0.0 and self.theta == 0.0


@dataclass
class Observation:
    """One synchronised snapshot of the robot."""

    stamp: float  # seconds, monotonic (sim time in simulation)
    images: dict[str, np.ndarray] = field(default_factory=dict)  # "front", "wrist"
    arm: dict[str, float] = field(default_factory=dict)  # joint name -> position
    base_velocity: BaseVelocity = field(default_factory=BaseVelocity)


@runtime_checkable
class Robot(Protocol):
    """Everything the rest of the code is allowed to ask of the hardware."""

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def get_observation(self) -> Observation: ...

    def drive(self, velocity: BaseVelocity) -> None:
        """Command the base. The arm holds its last target."""

    def move_arm(self, joints: Mapping[str, float]) -> None:
        """Command arm joint targets. The base is stopped."""

    def stop(self) -> None:
        """Zero base velocity, arm holds position."""


@runtime_checkable
class Perception(Protocol):
    def perceive(self, obs: Observation) -> Scene: ...


@runtime_checkable
class PickSkill(Protocol):
    """Grasp the object sitting at the canonical pre-grasp pose. Blocking."""

    def run(self, robot: Robot, target: Target) -> bool: ...


@runtime_checkable
class DropSkill(Protocol):
    """Release the held object into the station in front of the robot. Blocking."""

    def run(self, robot: Robot, category: Category) -> bool: ...
