"""Find an object in an image with no model at all: by what changed since the floor was empty.

Two images taken from the same place, one with the object on the floor and one without, differ
only where the object is. Our recorded pick episodes give such pairs for free: the base does
not move, the object lies on the floor in the first image and is gone from it in the last.
This is how the detector gets training boxes on the robot's own camera without anyone drawing
them.
"""

from __future__ import annotations

import cv2
import numpy as np


def box_by_difference(
    image_rgb: np.ndarray,
    empty_rgb: np.ndarray,
    threshold: int = 28,
    min_area_px: int = 500,
    max_share: float = 0.5,
) -> tuple[float, float, float, float] | None:
    """Box (x1, y1, x2, y2) around what `image_rgb` shows and `empty_rgb` does not, or None.

    The exposure may drift between the two images: the empty one is first brought to the same
    overall brightness. Small specks (video noise on a textured floor) are ignored, and so is a
    change covering most of the picture (the camera moved: these are not a pair).
    """
    image, empty = image_rgb.astype(np.int16), empty_rgb.astype(np.int16)
    empty = empty + (np.median(image, axis=(0, 1)) - np.median(empty, axis=(0, 1)))
    change = np.abs(image - empty).max(axis=2).clip(0, 255).astype(np.uint8)
    mask = (cv2.GaussianBlur(change, (5, 5), 0) > threshold).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = (int(v) for v in stats[best])
    if area < min_area_px or w * h > max_share * mask.size:
        return None
    return float(x), float(y), float(x + w), float(y + h)
