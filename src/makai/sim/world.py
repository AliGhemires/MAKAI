"""Tiny 2D kinematic simulator: lets everyone run the whole mission without the robot.

It fakes the three things that need hardware (base motion, perception, pick/drop)
behind the exact same contracts as the real implementations, so the state machine
and the navigation code are the real ones.
"""

from __future__ import annotations

import math
import random
import time
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
    # Direction each station's front faces, in the world frame (optional).
    station_facing: dict[Category, float] = field(default_factory=dict)

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
    """Each `get_observation()` advances the world by one control period.

    `slip` and `yaw_drift` make the wheels lie, as real omni wheels do: the base really moves
    `slip` less than it reports, and turns `yaw_drift` rad for every metre driven. The
    observation still reports the commanded velocity, so the odometry drifts.
    """

    def __init__(self, world: SimWorld, dt: float = 1 / 30, slip: float = 0.0, yaw_drift: float = 0.0):
        self.world, self.dt, self.slip, self.yaw_drift = world, dt, slip, yaw_drift
        self._vel = BaseVelocity()
        self.arm: dict[str, float] = {}

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def get_observation(self) -> Observation:
        v = self._vel
        keep = 1.0 - self.slip
        real = BaseVelocity(v.x * keep, v.y * keep, v.theta * keep + self.yaw_drift * math.hypot(v.x, v.y))
        self.world.advance(real, self.dt)
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
        classify_range_m: float | None = None,  # beyond it the category is a guess, as on the robot
        guess: Category = Category.CLOTHING,
        noise_m: float = 0.003,
        seed: int = 0,
    ):
        self.world = world
        self.half_fov = math.radians(hfov_deg) / 2
        self.min_range, self.max_range, self.noise = min_range_m, max_range_m, noise_m
        self.station_max_range = station_max_range_m
        self.classify_range, self.guess = classify_range_m, guess
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
                if self.classify_range is not None and math.hypot(*pos) > self.classify_range:
                    targets.append(Target(self.guess, obj.label, pos[0], pos[1], confidence=0.0))
                else:
                    targets.append(Target(obj.category, obj.label, pos[0], pos[1]))
        stations = {}
        for category, (sx, sy) in self.world.stations.items():
            if (pos := self._see(sx, sy, self.station_max_range)) is not None:
                facing = self.world.station_facing.get(category)
                if facing is not None:
                    facing = (facing - self.world.yaw + math.pi) % (2 * math.pi) - math.pi
                stations[category] = StationSighting(category, pos[0], pos[1], facing)
        return Scene(tuple(targets), stations)


def _wait(robot: Robot, seconds: float) -> None:
    """Let simulated time pass, in real time, while a skill 'works' (the base is stopped)."""
    dt = getattr(robot, "dt", 1 / 30)
    for _ in range(int(seconds / dt)):
        robot.get_observation()
        time.sleep(dt)


class SimPick:
    """Succeeds with probability `success_rate` if an object sits at the pre-grasp pose."""

    def __init__(
        self, world: SimWorld, goal_xy=(0.22, 0.0), reach_tol_m=0.03, success_rate=1.0, seed=0, duration_s=0.0
    ):
        self.world, self.goal, self.tol, self.rate = world, goal_xy, reach_tol_m, success_rate
        self.rng = random.Random(seed)
        self.attempts = 0
        self.duration_s = duration_s  # a real grasp takes seconds: lets the control page show it

    def run(self, robot: Robot, target: Target) -> bool:
        self.attempts += 1
        robot.stop()
        _wait(robot, self.duration_s)
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

    def __init__(self, world: SimWorld, reach_m: float = 0.45, duration_s: float = 0.0):
        self.world, self.reach, self.duration_s = world, reach_m, duration_s

    def run(self, robot: Robot, category: Category) -> bool:
        robot.stop()
        _wait(robot, self.duration_s)
        if self.world.carrying is None:
            return False
        # The object falls into the nearest station within reach in front of the robot.
        within = []
        for station_category, (sx, sy) in self.world.stations.items():
            bx, by = self.world.to_base(sx, sy)
            if bx > 0 and math.hypot(bx, by) <= self.reach:
                within.append((math.hypot(bx, by), station_category))
        if within:
            self.world.delivered.append((self.world.carrying, min(within)[1]))
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


def facing_world() -> SimWorld:
    """The other way to set up the zone: the robot starts at its near edge and the bin stands
    across it, 2.35 m ahead, its marker facing the robot. Nothing behind the start pose."""
    return SimWorld(
        objects=[
            SimObject(1.25, -0.50, Category.TRASH, "can"),
            SimObject(0.90, 0.15, Category.CLOTHING, "sock"),
            SimObject(1.55, 0.55, Category.TRASH, "can"),
            SimObject(0.60, 0.60, Category.CLOTHING, "sock"),
        ],
        stations={Category.TRASH: (2.35, 0.0)},
        station_facing={Category.TRASH: math.pi},
    )


def sweep_world() -> SimWorld:
    """A room to sweep: the robot starts at the origin, the bin just behind it, a laundry
    basket beside the bin, and a few things on the floor."""
    return SimWorld(
        objects=[
            SimObject(1.45, -0.55, Category.TRASH, "can"),
            SimObject(1.10, 0.10, Category.CLOTHING, "sock"),
            SimObject(1.90, 0.60, Category.TRASH, "can"),
            SimObject(0.75, 0.65, Category.CLOTHING, "sock"),
        ],
        stations={Category.TRASH: (-0.35, 0.0), Category.CLOTHING: (-0.35, 0.7)},
        station_facing={Category.TRASH: 0.0, Category.CLOTHING: 0.0},
    )
