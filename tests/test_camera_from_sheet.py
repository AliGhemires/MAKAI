"""Camera calibration from one sheet: recovers a known camera from its 4 corners."""

import importlib.util
import math
from pathlib import Path

import numpy as np

from makai.perception.geometry import CameraModel

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "camera_from_sheet.py"
spec = importlib.util.spec_from_file_location("makai_camera_from_sheet", SCRIPT)
camera_from_sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera_from_sheet)

TRUE = CameraModel(hfov_deg=46.0, height_m=0.22, pitch_deg=28.0, x_offset_m=0.07)


def corners(along: float, across: float, x0: float, y0: float, turn_deg: float) -> np.ndarray:
    """Pixels of a rectangle on the floor: near-left, near-right, far-right, far-left."""
    c, s = math.cos(math.radians(turn_deg)), math.sin(math.radians(turn_deg))
    local = [(0, across / 2), (0, -across / 2), (along, -across / 2), (along, across / 2)]
    return np.array([TRUE.project(np.array([x0 + c * x - s * y, y0 + s * x + c * y, 0.0])) for x, y in local])


def test_recovers_the_camera_from_a_turned_off_centre_sheet():
    cam = camera_from_sheet.fit_camera(corners(0.26, 0.18, 0.42, 0.03, -10), 0.26, 0.18, (640, 480))
    assert abs(cam["hfov_deg"] - 46.0) < 0.5
    assert abs(cam["height_m"] - 0.22) < 0.003
    assert abs(cam["pitch_deg"] - 28.0) < 0.3
    assert abs(cam["roll_deg"]) < 0.3
    assert cam["error_px"] < 0.1


def test_tape_marks_give_the_origin_shift():
    fitted = CameraModel(hfov_deg=46.0, height_m=0.22, pitch_deg=28.0, x_offset_m=0.05)  # origin 2 cm off
    marks = [
        (name, *TRUE.project(np.array([x, y, 0.0])), x, y)
        for name, x, y in [("A", 0.4, 0.0), ("B", 0.7, 0.1)]
    ]
    assert abs(camera_from_sheet.check_against_marks(fitted, marks) - 0.02) < 1e-3
