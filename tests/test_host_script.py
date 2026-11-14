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
