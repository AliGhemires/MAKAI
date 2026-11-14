"""Tiny 2D kinematic simulator: lets everyone run the whole mission without the robot.

It fakes the three things that need hardware (base motion, perception, pick/drop)
behind the exact same contracts as the real implementations, so the state machine
and the navigation code are the real ones.
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass, field

from makai.contracts import (
    BaseVelocity,
    Category,
    Observation,
    Robot,
    Scene,
    StationSighting,
    Target,
)


@dataclass
class SimObject:
    x: float
    y: float
    category: Category
    label: str = "object"


@dataclass
class SimWorld:
    objects: list[SimObject] = field(default_factory=list)
    stations: dict[Category, tuple[float, float]] = field(default_factory=dict)
    # Robot pose in the world frame.
    x: float = 0.0
    y: float = 0.0
    yaw: float = 0.0
    time: float = 0.0
    carrying: SimObject | None = None
    delivered: list[tuple[SimObject, Category]] = field(default_factory=list)

    def to_base(self, wx: float, wy: float) -> tuple[float, float]:
        dx, dy = wx - self.x, wy - self.y
        c, s = math.cos(-self.yaw), math.sin(-self.yaw)
        return c * dx - s * dy, s * dx + c * dy

    def advance(self, vel: BaseVelocity, dt: float) -> None:
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        self.x += (c * vel.x - s * vel.y) * dt
        self.y += (s * vel.x + c * vel.y) * dt
        self.yaw += vel.theta * dt
        self.time += dt


class SimRobot(Robot):
    """Each `get_observation()` advances the world by one control period."""

    def __init__(self, world: SimWorld, dt: float = 1 / 30):
        self.world, self.dt = world, dt
        self._vel = BaseVelocity()
        self.arm: dict[str, float] = {}

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def get_observation(self) -> Observation:
        self.world.advance(self._vel, self.dt)
        return Observation(stamp=self.world.time, arm=dict(self.arm), base_velocity=self._vel)

    def drive(self, velocity: BaseVelocity) -> None:
        self._vel = velocity

    def move_arm(self, joints: Mapping[str, float]) -> None:
        self._vel = BaseVelocity()
        self.arm.update(joints)

    def stop(self) -> None:
        self._vel = BaseVelocity()


class SimPerception:
    """Sees objects and stations inside the camera's field of view, with noise."""

    def __init__(
        self,
        world: SimWorld,
        hfov_deg: float = 55.0,
        min_range_m: float = 0.12,
        max_range_m: float = 2.5,
        station_max_range_m: float = 3.0,
        noise_m: float = 0.003,
        seed: int = 0,
    ):
        self.world = world
        self.half_fov = math.radians(hfov_deg) / 2
        self.min_range, self.max_range, self.noise = min_range_m, max_range_m, noise_m
        self.station_max_range = station_max_range_m
        self.rng = random.Random(seed)

    def _see(self, wx: float, wy: float, max_range: float) -> tuple[float, float] | None:
        bx, by = self.world.to_base(wx, wy)
        dist = math.hypot(bx, by)
        if not (self.min_range <= dist <= max_range) or abs(math.atan2(by, bx)) > self.half_fov:
            return None
        return bx + self.rng.gauss(0, self.noise), by + self.rng.gauss(0, self.noise)

    def perceive(self, obs: Observation) -> Scene:
        targets = []
        for obj in self.world.objects:
            if (pos := self._see(obj.x, obj.y, self.max_range)) is not None:
                targets.append(Target(obj.category, obj.label, pos[0], pos[1]))
        stations = {}
        for category, (sx, sy) in self.world.stations.items():
            if (pos := self._see(sx, sy, self.station_max_range)) is not None:
                stations[category] = StationSighting(category, pos[0], pos[1])
        return Scene(tuple(targets), stations)


class SimPick:
    """Succeeds with probability `success_rate` if an object sits at the pre-grasp pose."""

    def __init__(self, world: SimWorld, goal_xy=(0.22, 0.0), reach_tol_m=0.03, success_rate=1.0, seed=0):
        self.world, self.goal, self.tol, self.rate = world, goal_xy, reach_tol_m, success_rate
        self.rng = random.Random(seed)
        self.attempts = 0

    def run(self, robot: Robot, target: Target) -> bool:
        self.attempts += 1
        robot.stop()
        for obj in self.world.objects:
            bx, by = self.world.to_base(obj.x, obj.y)
            if math.hypot(bx - self.goal[0], by - self.goal[1]) <= self.tol:
                if self.rng.random() > self.rate:
                    return False
                self.world.objects.remove(obj)
                self.world.carrying = obj
                return True
        return False


class SimDrop:
    """Succeeds if the robot holds something and a station is within reach in front of it."""

    def __init__(self, world: SimWorld, reach_m: float = 0.45):
        self.world, self.reach = world, reach_m

    def run(self, robot: Robot, category: Category) -> bool:
        robot.stop()
        if self.world.carrying is None:
            return False
        for station_category, (sx, sy) in self.world.stations.items():
            bx, by = self.world.to_base(sx, sy)
            if bx > 0 and math.hypot(bx, by) <= self.reach:
                self.world.delivered.append((self.world.carrying, station_category))
                self.world.carrying = None
                return True
        return False


def demo_world() -> SimWorld:
    """A small room: four things on the floor, a laundry basket and a bin."""
    return SimWorld(
        objects=[
            SimObject(1.2, 0.4, Category.CLOTHING, "sock"),
            SimObject(0.9, -0.8, Category.TRASH, "can"),
            SimObject(-0.7, 0.9, Category.CLOTHING, "t-shirt"),
            SimObject(-1.0, -0.6, Category.TRASH, "paper ball"),
        ],
        stations={Category.CLOTHING: (1.8, 1.6), Category.TRASH: (1.8, -1.6)},
    )
