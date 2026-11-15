"""Host-mode odometry counted on the wheel encoders, and the base's flight recorder."""

import importlib.util
import math
import random
from pathlib import Path

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity
from makai.navigation.odometry import MAX_GAP_S, Odometry
from makai.robot.lekiwi import BaseGeometry, EncoderMotion, LeKiwiRobot, keep_host_extras
from makai.robot.trace import FIELDS, OdometryTrace

GEOMETRY = BaseGeometry.from_config(yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())["robot"]["base"])
STEPS_PER_RAD = 4096 / (2 * math.pi)


def wheels_after(turn_rad: float = 0.0, forward_m: float = 0.0, start=(100.0, 4000.0, 2048.0)) -> dict:
    """Encoder readings once the base has turned and driven that much from `start`."""
    rim = [
        math.cos(a) * forward_m + GEOMETRY.base_radius_m * turn_rad for a in GEOMETRY.angles_rad
    ]  # metres at the rim of each wheel
    steps = [r / GEOMETRY.wheel_radius_m * STEPS_PER_RAD for r in rim]
    return {name: (s0 + s) % 4096 for name, s0, s in zip(GEOMETRY.names, start, steps, strict=True)}


def test_integrating_the_velocity_gives_back_what_the_wheels_turned():
    motion, odometry = EncoderMotion(GEOMETRY), Odometry()
    rng, t, turned = random.Random(1), 10.0, 0.0
    odometry.update(motion.velocity(wheels_after(0.0), t), t)
    for _ in range(400):  # irregular observations, and wheels that cross the 4095 -> 0 mark many times
        t += rng.choice([0.0156, 0.0312, 0.0469])
        turned += rng.uniform(0.0, 0.03)
        odometry.update(motion.velocity(wheels_after(turned), t), t)
    assert turned > 4.0  # several wheel turns
    assert odometry.yaw == pytest.approx(turned, abs=1e-6)
    assert math.hypot(odometry.x, odometry.y) < 1e-6


def test_two_readings_in_the_same_clock_tick_lose_nothing():
    motion, odometry = EncoderMotion(GEOMETRY), Odometry()
    for stamp, forward in [(1.0, 0.0), (1.0156, 0.004), (1.0156, 0.009), (1.0156, 0.012), (1.0312, 0.016)]:
        odometry.update(
            motion.velocity(wheels_after(forward_m=forward), stamp), stamp
        )  # Windows: 15.6 ms ticks
    assert odometry.x == pytest.approx(0.016, abs=1e-5) and abs(odometry.y) < 1e-6


def test_the_scale_factors_still_apply():
    motion, odometry = EncoderMotion(GEOMETRY, speed_scale=(0.978, 1.04)), Odometry()
    for i in range(51):
        stamp = 5.0 + i / 30
        odometry.update(motion.velocity(wheels_after(turn_rad=i * 0.02, forward_m=i * 0.002), stamp), stamp)
    assert odometry.yaw == pytest.approx(1.04 * 1.0, abs=1e-6)


class HostClient:
    """LeRobot's client, as far as we use it: it keeps only the fields it knows."""

    def __init__(self, with_encoders: bool):
        self.with_encoders, self.turned, self.noise = with_encoders, 0.0, 0.0
        self.sent = None

    def _parse_observation(self, frames):
        return frames  # the real one decodes a JSON header and the JPEG frames

    def get_observation(self):
        header = {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": self.noise, "front": None}
        if self.with_encoders:
            header |= {f"{name}.enc": int(v) for name, v in wheels_after(self.turned).items()}
            header["host.time"] = 123.4
        observation = self._parse_observation(header)
        return {key: observation[key] for key in ("x.vel", "y.vel", "theta.vel")}

    def send_action(self, action):
        self.sent = action


def test_through_the_host_the_robot_counts_encoders_when_they_come():
    client = HostClient(with_encoders=True)
    keep_host_extras(client)
    robot, odometry = LeKiwiRobot(client, ("front",), geometry=GEOMETRY), Odometry()
    for i in range(60):
        client.turned = min(i, 40) * math.radians(1.0)  # 40 degrees, then standing still
        client.noise = 0.6 if i > 40 else 34.0  # the speed readings: wrong while moving, noisy at rest
        observation = robot.get_observation()
        odometry.update(observation.base_velocity, observation.stamp)
    assert robot.odometry_source == "wheel encoders, through the host"
    assert math.degrees(odometry.yaw) == pytest.approx(40.0, abs=0.2)  # a step is 0.09 degrees of wheel
    assert robot.raw_observation["theta.vel"] == 0.6  # what the policies see is LeRobot's, untouched
    assert math.degrees(robot.speed_reading.theta) == pytest.approx(0.6)
    assert robot.host_wheel_positions() is not None and client.host_extras["host.time"] == 123.4


def test_with_an_older_host_the_speed_readings_are_used_and_it_says_so():
    client = HostClient(with_encoders=False)
    keep_host_extras(client)
    robot = LeKiwiRobot(client, ("front",), geometry=GEOMETRY)
    client.noise = 10.0
    observation = robot.get_observation()
    assert math.degrees(observation.base_velocity.theta) == pytest.approx(10.0)
    assert robot.host_wheel_positions() is None and "update it on the Pi" in robot.odometry_source


def test_a_long_silence_is_not_integrated():
    odometry = Odometry()
    odometry.update(BaseVelocity(), 0.0)
    odometry.update(BaseVelocity(x=0.1), 0.05)
    # A pick lasted 15 s, base stopped. The first reading after it is noise: one wheel at 50 steps/s.
    odometry.update(BaseVelocity(theta=math.radians(0.586)), 15.05)
    assert odometry.yaw == 0.0 and odometry.x == pytest.approx(0.005)  # it used to jump by 8.8 degrees
    odometry.update(BaseVelocity(theta=0.5), 15.05 + MAX_GAP_S)  # a slow step is still counted
    assert odometry.yaw == pytest.approx(0.5 * MAX_GAP_S)


def load_report():
    path = Path(__file__).resolve().parents[1] / "scripts" / "odometry_report.py"
    spec = importlib.util.spec_from_file_location("odometry_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_trace_records_moves_and_the_report_compares_the_sources(tmp_path):
    trace = OdometryTrace(tmp_path / "trace.csv", idle_s=1.0)
    t, turned = 100.0, 0.0
    for i in range(400):
        t += 1 / 30
        moving = 60 <= i < 180  # 4 s at 30 deg/s: a turn of 120 degrees
        command = BaseVelocity(theta=math.radians(30.0)) if moving else BaseVelocity()
        turned += math.radians(1.0) if moving else 0.0
        speed = BaseVelocity(theta=math.radians(31.0 if moving else 0.0))  # readings 3 % too high
        trace.note(t, t - 50.0, command, speed, wheels_after(turned), (0.0, 0.0, turned))
    trace.close()
    lines = (tmp_path / "trace.csv").read_text().splitlines()
    assert lines[0].split(",") == list(FIELDS)
    assert 140 < len(lines) - 1 < 160  # the move and the second after it, not the 13 s of standing still

    report = load_report()
    moves = [report.describe(m, GEOMETRY) for m in report.split_moves(report.load(tmp_path / "trace.csv"))]
    assert len(moves) == 1 and moves[0]["kind"] == "turn"
    assert moves[0]["cmd"][2] == pytest.approx(120.0, abs=1.5)
    assert moves[0]["encoders"][2] == pytest.approx(120.0, abs=1.5)
    assert moves[0]["speed"][2] / moves[0]["encoders"][2] == pytest.approx(1.033, abs=0.01)
    left, back, right = moves[0]["wheels"]
    assert left == pytest.approx(back, abs=2) and back == pytest.approx(right, abs=2)  # a turn on the spot
