"""Find things on the floor without recognising them: anything that is not floor-coloured.

The venue floor is an orange/brown carpet. Asking "what is not carpet?" turned out far more
reliable than asking an open-vocabulary detector "where is the sock?" (7/7 against 3/7 on our
first phone photos, 14 Nov). No model, no training, a few milliseconds per image.

Limits:
- an object of the carpet's own colour is invisible: demo objects must contrast with the floor;
- anything else lying on the floor (cable, bag, foot) is reported too: `CameraPerception`
  filters by distance and by physical size, and the demo area must be clear;
- the colour thresholds were tuned on phone photos in daylight: re-check them with the
  robot camera and under the evening lighting (`scripts/detect.py --detector floor`).

What the object *is* (clothing or not) is a separate question, answered by an optional
`CropClassifier` on the cropped object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

from makai.contracts import Category, Detection


@dataclass(frozen=True)
class FloorColor:
    """HSV range of the floor (OpenCV convention: hue 0..179, saturation and value 0..255)."""

    hue_max: int = 25  # orange/brown: hue <= hue_max ...
    hue_wrap_min: int = 170  # ... or >= hue_wrap_min (reds wrap around 180)
    sat_min: int = 50  # below this it is grey, white or black: not carpet
    val_min: int = 45  # below this it is black, even in shadow the carpet stays above

    def mask(self, image_rgb: np.ndarray) -> np.ndarray:
        """True where the pixel looks like floor."""
        hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
        hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        return (
            ((hue <= self.hue_max) | (hue >= self.hue_wrap_min))
            & (sat >= self.sat_min)
            & (val >= self.val_min)
        )


class CropClassifier(Protocol):
    def classify(self, crop_rgb: np.ndarray) -> tuple[Category, float]:
        """Category of the object filling the crop, and a confidence in [0, 1]."""


def _odd(value: float, minimum: int) -> int:
    size = max(minimum, int(round(value)))
    return size if size % 2 else size + 1


class FloorBlobDetector:
    def __init__(
        self,
        floor: FloorColor | None = None,
        classifier: CropClassifier | None = None,
        default_category: Category = Category.CLOTHING,
        min_area_fraction: float = 0.002,  # of the image: smaller is noise
        max_area_fraction: float = 0.20,  # larger is furniture, a wall, or the robot itself
        ignore_top_fraction: float = 0.0,  # blobs starting in this top band are background, not floor
        crop_margin: float = 0.2,
        max_objects: int = 10,
    ):
        self.floor = floor or FloorColor()
        self.classifier, self.default_category = classifier, default_category
        self.min_area_fraction, self.max_area_fraction = min_area_fraction, max_area_fraction
        self.ignore_top_fraction, self.crop_margin, self.max_objects = (
            ignore_top_fraction,
            crop_margin,
            max_objects,
        )

    def object_mask(self, image_rgb: np.ndarray) -> np.ndarray:
        """uint8 mask, 255 where something that is not floor stands."""
        width = image_rgb.shape[1]
        mask = (~self.floor.mask(image_rgb)).astype(np.uint8) * 255
        # Remove speckle, then fill small holes (folds, highlights) inside objects.
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((_odd(width / 96, 3),) * 2, np.uint8))
        return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((_odd(width / 53, 5),) * 2, np.uint8))

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        height, width = image_rgb.shape[:2]
        count, _, stats, _ = cv2.connectedComponentsWithStats(self.object_mask(image_rgb))
        blobs = []
        for x, y, w, h, area in stats[1:count]:
            fraction = area / (width * height)
            if not self.min_area_fraction <= fraction <= self.max_area_fraction:
                continue
            if y < self.ignore_top_fraction * height:
                continue
            blobs.append((int(area), int(x), int(y), int(w), int(h)))
        blobs.sort(reverse=True)

        detections = []
        for _, x, y, w, h in blobs[: self.max_objects]:
            category, confidence = self.default_category, 1.0
            if self.classifier is not None:
                margin = int(self.crop_margin * max(w, h))
                crop = image_rgb[max(0, y - margin) : y + h + margin, max(0, x - margin) : x + w + margin]
                category, confidence = self.classifier.classify(crop)
                if category is Category.UNKNOWN:
                    # Too far to tell what it is: report it anyway, so the robot comes closer.
                    category, confidence = self.default_category, 0.0
            detections.append(Detection("object", category, confidence, (x, y, x + w, y + h)))
        return detections
