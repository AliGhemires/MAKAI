"""Boxes with no model: what differs between an image and its empty twin."""

import numpy as np

from makai.perception.autolabel import box_by_difference


def floor(seed: int = 0) -> np.ndarray:
    """A speckled floor, like our carpet."""
    return np.random.default_rng(seed).integers(120, 150, (480, 640, 3)).astype(np.uint8)


def test_the_box_is_where_the_object_is():
    empty = floor()
    image = empty.copy()
    image[300:380, 200:330] = (30, 60, 140)  # a blue can on the floor
    x1, y1, x2, y2 = box_by_difference(image, empty)
    assert abs(x1 - 200) <= 6 and abs(y1 - 300) <= 6 and abs(x2 - 330) <= 6 and abs(y2 - 380) <= 6


def test_a_change_of_exposure_is_not_an_object():
    empty = floor()
    image = empty.copy()
    image[300:380, 200:330] = (30, 60, 140)
    brighter = np.clip(empty.astype(int) + 25, 0, 255).astype(np.uint8)  # the camera opened up a little
    box = box_by_difference(image, brighter)
    assert box is not None and abs(box[0] - 200) <= 6 and abs(box[2] - 330) <= 6
    assert box_by_difference(empty, brighter) is None


def test_noise_and_a_moved_camera_give_no_box():
    assert box_by_difference(floor(0), floor(1)) is None  # two views of nothing: only the speckle differs
    moved = floor()
    moved[100:460, 40:600] = (30, 60, 140)  # most of the picture changed: not a pair
    assert box_by_difference(moved, floor()) is None
