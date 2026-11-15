"""The bin marked with a white U in a dark square, seen by the robot's low camera."""

import math

import cv2
import numpy as np
import pytest
import yaml

from makai.config import CONFIG_DIR, REPO_ROOT
from makai.contracts import Category
from makai.perception.geometry import CameraModel
from makai.perception.stations import UPatternDetector, build_station_detector

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())["perception"]
CAMERA = CameraModel(**COMMITTED["camera_model"])
FLOOR, WALL, CARDBOARD, DARK, WHITE = (
    (190, 150, 90),
    (205, 203, 198),
    (150, 120, 85),
    (62, 62, 60),
    (235, 235, 230),
)
U_M = 0.044  # outer width of the U


def paint(image: np.ndarray, x: float, y0: float, y1: float, z0: float, z1: float, colour) -> None:
    """A rectangle standing at `x` metres ahead, from y0 to y1 (left positive) and z0 to z1 (up)."""
    corners = [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    pixels = np.array([CAMERA.project(np.array(c)) for c in corners]).round().astype(np.int32)
    cv2.fillPoly(image, [pixels], colour)


def scene(x: float | None, y: float = 0.0) -> np.ndarray:
    """The floor, the wall, and a box whose face is `x` metres ahead with the pattern on it."""
    image = np.full((CAMERA.height, CAMERA.width, 3), WALL, dtype=np.uint8)
    horizon = int(CAMERA.project(np.array([50.0, 0.0, 0.0]))[1])
    image[horizon:] = FLOOR
    if x is None:
        return image
    paint(image, x, y + 0.25, y - 0.25, 0.0, 0.30, CARDBOARD)
    paint(image, x, y + 0.035, y - 0.035, 0.065, 0.135, DARK)  # the square, 7 cm
    half, bar, z0 = U_M / 2, 0.010, 0.077
    paint(image, x, y + half, y + half - bar, z0, z0 + U_M, WHITE)  # left arm
    paint(image, x, y - half + bar, y - half, z0, z0 + U_M, WHITE)  # right arm
    paint(image, x, y + half, y - half, z0, z0 + bar, WHITE)  # bottom
    return image


def rgb(image_bgr: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    "distance, side",
    [(0.35, 0.0), (0.40, 0.03), (0.80, 0.10), (1.30, 0.10), (2.00, -0.20), (2.40, 0.30)],
)
def test_the_pattern_is_found_and_its_distance_read(distance, side):
    """From the dock (35 cm, straight ahead) to across the zone, a little to the side."""
    found = UPatternDetector(CAMERA, Category.TRASH, U_M).detect(scene(distance, y=side))
    sighting = found[Category.TRASH]
    # The U is 15 px wide at 2.4 m: one pixel is 7 % of its distance there.
    assert sighting.x_m == pytest.approx(distance, rel=0.06 if distance < 2.0 else 0.10)
    assert math.degrees(math.atan2(sighting.y_m, sighting.x_m)) == pytest.approx(
        math.degrees(math.atan2(side, distance)), abs=1.0
    )


def test_nothing_without_the_pattern():
    image = scene(None)
    paint(image, 0.8, 0.10, -0.10, 0.0, 0.0, DARK)  # nothing standing
    cv2.circle(image, (300, 400), 25, DARK, -1)  # a black sock on the floor
    cv2.circle(image, (300, 400), 6, WHITE, -1)  # with a white spot
    assert UPatternDetector(CAMERA, Category.TRASH, U_M).detect(image) == {}


def test_a_u_far_above_the_floor_is_not_the_bin():
    """A window pane framed by dark bars, behind the zone, can look like a U: its size puts it
    close, its place in the image puts it high up. Stuck 10 cm above the floor, it is the bin."""
    detector = UPatternDetector(CAMERA, Category.TRASH, U_M)
    image = scene(None)
    z0, half, bar = 0.24, U_M / 2, 0.010  # the same U, 26 cm up (near the top of the image), 1.2 m ahead
    paint(image, 1.2, 0.035, -0.035, z0 - 0.012, z0 + 0.058, DARK)
    paint(image, 1.2, half, half - bar, z0, z0 + U_M, WHITE)
    paint(image, 1.2, -half + bar, -half, z0, z0 + U_M, WHITE)
    paint(image, 1.2, half, -half, z0, z0 + bar, WHITE)
    assert detector.find(image) and detector.detect(image) == {}
    assert detector.detect(scene(1.2))[Category.TRASH].x_m == pytest.approx(1.2, rel=0.06)


def test_on_the_robots_camera():
    """15 Nov: the box 1.2 m ahead (measured on the floor), the pattern on it; then the same
    boxes 0.9 m ahead without it."""
    detector = UPatternDetector(CAMERA, Category.TRASH, U_M)
    seen = rgb(cv2.imread(str(REPO_ROOT / "docs/figures/stations_robot_camera_12m.jpg")))
    sighting = detector.detect(seen)[Category.TRASH]
    assert 1.1 < sighting.distance_m < 1.4 and abs(sighting.y_m) < 0.1
    empty = rgb(cv2.imread(str(REPO_ROOT / "docs/figures/stations_robot_camera_09m.jpg")))
    assert detector.detect(empty) == {}


def test_chosen_by_the_config():
    stations = {"kind": "pattern", "pattern": {"category": "trash", "u_width_m": 0.05}}
    detector = build_station_detector({"stations": stations}, CAMERA)
    assert isinstance(detector, UPatternDetector) and detector.category is Category.TRASH
    assert detector.u_width_m == 0.05
