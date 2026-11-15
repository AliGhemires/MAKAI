"""Stations marked with a strip of grey tape on a cardboard box, seen by the robot's low camera."""

from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import Category
from makai.perception.geometry import CameraModel
from makai.perception.stations import StationDetector, TapeStationDetector, build_station_detector

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())["perception"]
CAMERA = CameraModel(**COMMITTED["camera_model"])  # 7.5 cm above the floor, nearly level, 42 degrees wide
KINDS = {"horizontal": Category.CLOTHING, "vertical": Category.TRASH}
TAPE_M, LONG_M, TALL_M = 0.048, 0.41, 0.21  # the roll, the strip across one box, the upright one
FLOOR, WALL, CARDBOARD, TAPE = (190, 150, 90), (205, 203, 198), (150, 120, 85), (88, 84, 82)


def detector(**more) -> TapeStationDetector:
    lengths = {"horizontal": LONG_M, "vertical": TALL_M}
    return TapeStationDetector(CAMERA, KINDS, tape_width_m=TAPE_M, lengths_m=lengths, **more)


def paint(image: np.ndarray, x: float, y0: float, y1: float, z0: float, z1: float, colour) -> None:
    """A rectangle standing at `x` metres ahead, from y0 to y1 (left positive) and z0 to z1 (up)."""
    corners = [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]
    pixels = np.array([CAMERA.project(np.array(c)) for c in corners]).round().astype(np.int32)
    cv2.fillPoly(image, [pixels], colour)


def scene() -> np.ndarray:
    """The floor of the room up to the horizon, the wall above."""
    image = np.full((CAMERA.height, CAMERA.width, 3), WALL, dtype=np.uint8)
    horizon = int(CAMERA.project(np.array([50.0, 0.0, 0.0]))[1])
    image[horizon:] = FLOOR
    return image


def box(image: np.ndarray, x: float, y: float, strip: str, strip_y: float | None = None) -> None:
    """A cardboard box 50 cm wide and 21 cm tall whose front stands `x` m ahead, centred on `y`."""
    paint(image, x, y - 0.25, y + 0.25, 0.0, 0.21, CARDBOARD)
    if strip == "horizontal":
        paint(image, x, y - LONG_M / 2, y + LONG_M / 2, 0.08 - TAPE_M / 2, 0.08 + TAPE_M / 2, TAPE)
    else:
        at = y if strip_y is None else strip_y
        paint(image, x, at - TAPE_M / 2, at + TAPE_M / 2, 0.21 - TALL_M, 0.21, TAPE)


@pytest.mark.parametrize("ahead", [0.8, 1.2, 1.6, 2.0, 2.6])
def test_two_boxes_are_told_apart_and_placed(ahead):
    image = scene()
    box(image, ahead, 0.32, "horizontal")
    box(image, ahead, -0.30, "vertical")
    seen = detector().detect(image)
    assert set(seen) == {Category.CLOTHING, Category.TRASH}
    for category, y in ((Category.CLOTHING, 0.32), (Category.TRASH, -0.30)):
        assert seen[category].x_m == pytest.approx(ahead, rel=0.06)
        assert seen[category].y_m == pytest.approx(y, abs=0.04)
        assert seen[category].facing_rad is None  # a strip does not tell which way the box faces


def test_at_the_dock_the_strip_no_longer_fits_in_the_image_and_its_width_gives_the_distance():
    across = scene()
    box(across, 0.35, 0.0, "horizontal")  # 41 cm of strip, 23 cm of floor in view at that distance
    strips = detector().find_strips(across)
    assert len(strips) == 1 and strips[0].cut_start and strips[0].cut_end
    seen = detector().detect(across)[Category.CLOTHING]
    assert seen.x_m == pytest.approx(0.35, abs=0.03) and abs(seen.y_m) < 0.02

    upright = scene()
    box(upright, 0.35, 0.03, "vertical")
    seen = detector().detect(upright)[Category.TRASH]
    assert seen.x_m == pytest.approx(0.35, abs=0.03) and seen.y_m == pytest.approx(0.03, abs=0.015)


def test_a_strip_half_out_of_the_image_is_still_centred_right():
    image = scene()
    box(image, 0.9, 0.30, "horizontal")  # its left end is out of the image, its right end is in
    strip = detector().find_strips(image)[0]
    assert strip.cut_start and not strip.cut_end
    seen = detector().detect(image)[Category.CLOTHING]
    assert seen.y_m == pytest.approx(0.30, abs=0.04) and seen.x_m == pytest.approx(0.9, rel=0.08)


def test_the_strip_need_not_be_in_the_middle_of_the_box():
    image = scene()
    box(image, 1.5, 0.0, "vertical", strip_y=-0.12)  # as on our box: right of its middle
    seen = detector().detect(image)[Category.TRASH]
    assert seen.y_m == pytest.approx(-0.12, abs=0.03)  # the station is where the strip is


def test_what_is_not_a_strip_on_a_box_is_ignored():
    assert detector().detect(scene()) == {}  # an empty room
    grey_wall = scene()
    paint(grey_wall, 2.0, -1.0, 1.0, 0.05, 0.11, TAPE)  # a grey band along the wall: no cardboard beside it
    assert detector().detect(grey_wall) == {}
    on_the_floor = scene()
    cv2.rectangle(
        on_the_floor, (250, 300), (400, 318), TAPE, -1
    )  # a grey thing lying on the floor, 1 m ahead
    assert detector().detect(on_the_floor) == {}
    black = scene()
    box(black, 1.5, 0.0, "horizontal")
    paint(
        black, 1.5, -LONG_M / 2, LONG_M / 2, 0.056, 0.104, (20, 20, 22)
    )  # black, not grey: a sock, a shadow
    assert detector().detect(black) == {}
    bare = scene()
    paint(bare, 1.5, -0.25, 0.25, 0.0, 0.21, CARDBOARD)  # a box without tape
    assert detector().detect(bare) == {}


def floor_tape(image: np.ndarray, x0: float, x1: float, y0: float, y1: float) -> None:
    """A piece of grey tape stuck on the floor, from x0 to x1 ahead and y0 to y1 to the left."""
    corners = [(x0, y0, 0.0), (x0, y1, 0.0), (x1, y1, 0.0), (x1, y0, 0.0)]
    pixels = np.array([CAMERA.project(np.array(c)) for c in corners]).round().astype(np.int32)
    cv2.fillPoly(image, [pixels], TAPE)


@pytest.mark.parametrize("ahead", [0.6, 1.0, 1.4, 1.8, 2.2, 3.0, 4.0])
def test_tape_stuck_across_the_floor_is_not_a_box(ahead):
    image = scene()
    floor_tape(image, ahead, ahead + TAPE_M, -0.3, 0.3)  # beyond 1.8 m it used to pass for the clothing box
    assert detector().detect(image) == {}
    floor_tape(image, ahead, ahead + TAPE_M, -LONG_M / 2, LONG_M / 2)  # even as long as the real strip
    assert detector().detect(image) == {}


@pytest.mark.parametrize("far", [1.0, 2.0, 3.0, 5.0])
def test_a_line_of_tape_running_away_on_the_floor_is_not_a_box(far):
    image = scene()
    floor_tape(image, 0.5, far, -TAPE_M / 2, TAPE_M / 2)  # to 3 m it used to pass for the trash box
    assert detector().detect(image) == {}


def test_tape_on_the_floor_in_front_of_the_boxes_changes_nothing():
    image = scene()
    box(image, 2.0, 0.32, "horizontal")
    box(image, 2.0, -0.30, "vertical")
    floor_tape(image, 1.2, 1.2 + TAPE_M, -0.4, 0.4)
    floor_tape(image, 0.5, 1.6, 0.05, 0.05 + TAPE_M)
    seen = detector().detect(image)
    assert seen[Category.CLOTHING].x_m == pytest.approx(2.0, rel=0.06)
    assert seen[Category.TRASH].x_m == pytest.approx(2.0, rel=0.06)
    assert seen[Category.CLOTHING].y_m == pytest.approx(0.32, abs=0.04)


def test_only_the_configured_strips_are_stations():
    image = scene()
    box(image, 1.5, 0.3, "horizontal")
    box(image, 1.5, -0.3, "vertical")
    one = TapeStationDetector(CAMERA, {"vertical": Category.TRASH}, lengths_m={"vertical": TALL_M})
    assert set(one.detect(image)) == {Category.TRASH}


def test_the_photo_of_our_two_boxes():
    """A phone photo (not the robot's camera): the two strips are found and told apart."""
    photo = cv2.cvtColor(
        cv2.imread(str(Path(__file__).parent / "samples" / "bins_tape.jpg")), cv2.COLOR_BGR2RGB
    )
    strips = {s.kind: s for s in detector(horizon_margin_px=None).find_strips(photo)}
    assert set(strips) == {"horizontal", "vertical"}
    across, upright = strips["horizontal"], strips["vertical"]
    assert across.u < 320 < upright.u  # the strip lying flat is on the left box, the upright one on the right
    assert across.length_px == pytest.approx(283, abs=15) and across.length_px / across.thickness_px > 8
    assert upright.length_px == pytest.approx(144, abs=10) and upright.thickness_px == pytest.approx(
        33, abs=4
    )


def test_the_config_chooses_tape_or_markers():
    tape = build_station_detector(COMMITTED, CAMERA)
    assert isinstance(tape, TapeStationDetector)
    assert tape.kinds == {"horizontal": Category.CLOTHING, "vertical": Category.TRASH}
    assert tape.lengths_m["horizontal"] == 0.41 and tape.tape_width_m == 0.048
    markers = build_station_detector({"stations": COMMITTED["stations"] | {"kind": "aruco"}}, CAMERA)
    assert isinstance(markers, StationDetector) and markers.marker_ids == {
        0: Category.CLOTHING,
        1: Category.TRASH,
    }
