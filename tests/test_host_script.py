"""The Pi host script: our own flags are consumed and applied (no robot needed)."""

import runpy
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

lekiwi = pytest.importorskip("lerobot.robots.lekiwi.lekiwi")  # the CI installs the core only

HOST = str(Path(__file__).resolve().parents[1] / "scripts" / "lekiwi_host.py")


def load_host(monkeypatch, *flags: str) -> None:
    """Run the script's module level (not its main) and undo its patches after the test."""
    monkeypatch.setattr(cv2, "imencode", cv2.imencode)
    monkeypatch.setattr(lekiwi.LeKiwi, "configure", lekiwi.LeKiwi.configure)
    monkeypatch.setattr(lekiwi.LeKiwi, "get_observation", lekiwi.LeKiwi.get_observation)
    monkeypatch.setattr(sys, "argv", ["host", *flags, "--robot.id=makai_kiwi"])
    runpy.run_path(HOST, run_name="host")
    assert sys.argv == ["host", "--robot.id=makai_kiwi"]  # only LeRobot's arguments are left


def encode_like_the_host(image: np.ndarray) -> np.ndarray:
    ok, jpeg = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    return jpeg


@pytest.fixture
def frame() -> np.ndarray:
    noise = np.random.default_rng(0).integers(0, 255, (480, 640, 3), dtype=np.uint8)
    return cv2.GaussianBlur(noise, (0, 0), 2)


def test_jpeg_quality_flag_makes_frames_lighter(monkeypatch, frame):
    stock = encode_like_the_host(frame)
    load_host(monkeypatch, "--arm_acceleration=50", "--jpeg_quality=75")
    light = encode_like_the_host(frame)
    assert len(light) < 0.8 * len(stock)
    assert cv2.imdecode(light, cv2.IMREAD_COLOR).shape == frame.shape


def test_without_the_flag_frames_are_unchanged(monkeypatch, frame):
    stock = encode_like_the_host(frame)
    load_host(monkeypatch, "--arm_acceleration=50")
    assert len(encode_like_the_host(frame)) == len(stock)


def test_out_of_range_quality_is_refused(monkeypatch):
    with pytest.raises(SystemExit):
        load_host(monkeypatch, "--jpeg_quality=5")


def test_the_host_adds_the_wheel_encoders_and_its_clock(monkeypatch):
    class Bus:
        def __init__(self):
            self.fail = False

        def sync_read(self, register, motors, normalize=True):
            if self.fail:
                raise ConnectionError("no status packet")
            assert register == "Present_Position" and normalize is False
            return dict(zip(motors, (12, 4095, 2048), strict=True))

    class Robot:
        bus = Bus()
        base_motors = ["base_left_wheel", "base_back_wheel", "base_right_wheel"]

    monkeypatch.setattr(lekiwi.LeKiwi, "get_observation", lambda self: {"x.vel": 0.1, "front": "image"})
    load_host(monkeypatch, "--arm_acceleration=50")
    observation = lekiwi.LeKiwi.get_observation(Robot())
    assert observation["x.vel"] == 0.1 and observation["front"] == "image"  # LeRobot's part is untouched
    assert observation["base_left_wheel.enc"] == 12 and observation["base_back_wheel.enc"] == 4095
    assert observation["base_right_wheel.enc"] == 2048 and observation["host.time"] > 0
    import json

    json.dumps({k: v for k, v in observation.items() if k != "front"})  # what the host sends as a header
    Robot.bus.fail = True  # a failed read must not stop the stream: the laptop falls back on the speeds
    assert lekiwi.LeKiwi.get_observation(Robot()) == {"x.vel": 0.1, "front": "image"}
