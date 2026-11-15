"""Bases: remember where the robot is, drive anywhere, then go back there on odometry."""

import math

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Observation
from makai.robot.lekiwi import BaseGeometry
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver
from makai.robot.moves import GoTo, MoveSpec, wrap_angle

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
LIMITS = DriveLimits.from_config(COMMITTED["teleop"]["drive"])
DT = 0.02


class SpeedRobot:
    """Through the host: no encoders, the odometry integrates the measured speed. `scale`: how
    far the robot really goes compared with what it measures (slip)."""

    def __init__(self, scale=1.0):
        self.scale, self.t, self.v = scale, 0.0, BaseVelocity()
        self.true = [0.0, 0.0, 0.0]

    def drive(self, cmd):
        self.v = cmd
        c, s = math.cos(self.true[2]), math.sin(self.true[2])
        self.true[0] += self.scale * (c * cmd.x - s * cmd.y) * DT
        self.true[1] += self.scale * (s * cmd.x + c * cmd.y) * DT
        self.true[2] += self.scale * cmd.theta * DT
        self.t += DT

    def get_observation(self):
        return Observation(stamp=self.t, base_velocity=self.v)

    def stop(self):
        self.v = BaseVelocity()


def make(scale=1.0):
    robot = SpeedRobot(scale)
    loop = DriveLoop(robot, ManualDriver(LIMITS), GEOMETRY, telemetry_hz=50.0)
    loop.tick(0.0)
    return robot, loop


def run(loop, t, key, seconds=60.0):
    end = t + seconds
    while loop.snapshot()[key] is not None and t < end:
        t += DT
        loop.tick(t)
    return t + DT


def wander(loop, t):
    """Drive away with precise moves: forward, sideways, then a turn."""
    for spec in (MoveSpec("x", 0.4, 0.15), MoveSpec("y", 0.2, 0.1), MoveSpec("theta", math.radians(70), 0.6)):
        loop.tick(t)
        loop.start_move("pilot", spec, t)
        t = run(loop, t, "move")
    return t


def test_goes_back_to_the_base_with_its_heading():
    robot, loop = make()
    loop.define_base("1")
    t = wander(loop, 0.0)
    assert math.hypot(robot.true[0], robot.true[1]) > 0.4  # it did go away
    loop.go_base("pilot", "1", t)
    run(loop, t, "goto")
    result = loop.snapshot()["last_goto"]
    assert result["status"] == "done" and result["base"] == "1"
    assert math.hypot(robot.true[0], robot.true[1]) < 0.015  # back on the spot, odometry being exact here
    assert abs(math.degrees(wrap_angle(robot.true[2]))) < 2.0  # and facing the same way
    assert loop.commanded.is_zero()


def test_slipping_wheels_show_on_the_floor_not_in_the_odometry():
    """The point of the test on the real robot: odometry says 'arrived', the tape says how far."""
    robot, loop = make(scale=0.95)  # the robot really goes 5 % less than it measures
    loop.define_base("1")
    t = wander(loop, 0.0)
    loop.go_base("pilot", "1", t)
    run(loop, t, "goto")
    assert loop.snapshot()["last_goto"]["left_cm"] < 1.5  # odometry: arrived
    assert math.hypot(robot.true[0], robot.true[1]) > 0.005  # floor: not quite


def test_refused_without_the_base_or_after_a_reset():
    _, loop = make()
    with pytest.raises(ValueError, match="not set"):
        loop.go_base("pilot", "2", 0.0)
    loop.define_base("2")
    assert loop.snapshot()["bases"]["2"]["valid"]
    loop.reset_odometry()
    assert not loop.snapshot()["bases"]["2"]["valid"]
    with pytest.raises(ValueError, match="reset"):
        loop.go_base("pilot", "2", 0.0)


def test_cancel_and_emergency_stop_end_it_at_once():
    _, loop = make()
    loop.define_base("1")
    t = wander(loop, 0.0)
    loop.go_base("pilot", "1", t)
    for _ in range(10):
        t += DT
        loop.tick(t)
    loop.cancel_move()
    t += DT
    loop.tick(t)
    assert loop.snapshot()["goto"] is None and loop.snapshot()["last_goto"]["status"] == "cancelled"
    loop.go_base("pilot", "1", t)
    loop.driver.emergency_stop()
    t += DT
    loop.tick(t)
    assert loop.snapshot()["last_goto"]["status"] == "stopped" and loop.commanded.is_zero()


def test_goto_turns_the_short_way_and_times_out():
    goto = GoTo("1", (0.0, 0.0, math.radians(350)), (0.0, 0.0, 0.0), now=0.0)
    assert goto.step((0.0, 0.0, 0.0), 0.0).theta < 0  # 350 deg is -10 deg: turn right
    goto = GoTo("1", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), now=0.0)
    assert goto.step((0.0, 0.0, 0.0), 1000.0) is None and goto.status == "timeout"
