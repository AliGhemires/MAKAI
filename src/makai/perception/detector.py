"""Find things lying on the floor in the front camera image.

- `LearnedDetector`: our own small model, trained on our own images. The default.
- `OpenVocabDetector`: an Ultralytics open-vocabulary model (YOLOE / YOLO-World): you give
  it words, no training needed. Too weak on our objects (3 of 7 photos), kept for experiments.
- `makai.perception.floor.FloorBlobDetector`: anything that is not floor-coloured. No model,
  but breaks when the lighting changes; used to label the very first training images.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

import numpy as np

from makai.config import REPO_ROOT
from makai.contracts import Category, Detection


class Detector(Protocol):
    def detect(self, image_rgb: np.ndarray) -> list[Detection]: ...


def category_of(label: str, prompts: Mapping[Category, list[str]]) -> Category:
    for category, labels in prompts.items():
        if label in labels:
            return category
    return Category.UNKNOWN


class OpenVocabDetector:
    def __init__(
        self,
        prompts: Mapping[Category, list[str]],
        model: str = "yoloe-11s-seg.pt",
        confidence: float = 0.15,
        device: str | None = None,
        max_box_fraction: float = 0.5,
    ):
        from ultralytics import YOLO  # heavy import: only when a real detector is built

        self.prompts = {Category(k): list(v) for k, v in prompts.items()}
        self.labels = [label for labels in self.prompts.values() for label in labels]
        self.confidence, self.device, self.max_box_fraction = confidence, device, max_box_fraction
        self.model = YOLO(model)
        if hasattr(self.model, "set_classes") and self._is_open_vocab(model):
            if hasattr(self.model, "get_text_pe"):  # YOLOE
                self.model.set_classes(self.labels, self.model.get_text_pe(self.labels))
            else:  # YOLO-World
                self.model.set_classes(self.labels)

    @staticmethod
    def _is_open_vocab(model: str) -> bool:
        return "yoloe" in model.lower() or "world" in model.lower()

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        return _predict(
            self.model,
            image_rgb,
            self.confidence,
            self.device,
            self.max_box_fraction,
            lambda label: category_of(label, self.prompts),
        )


class LearnedDetector:
    """Our own small detector, trained on our own images with `scripts/train_detector.py`.

    Its class names are the category values ("clothing", "trash"), so it finds the object and
    says what it is in one pass. Trained with heavy lighting changes: this is the detector that
    holds up when the light changes (docs/workstreams/WS2_perception.md).
    """

    def __init__(
        self,
        weights: str | Path,
        confidence: float = 0.2,
        device: str | None = None,
        max_box_fraction: float = 0.5,
    ):
        from ultralytics import YOLO  # heavy import: only when a real detector is built

        path = Path(weights) if Path(weights).is_absolute() else REPO_ROOT / weights
        if not path.exists():
            raise FileNotFoundError(f"detector weights not found: {path} (git pull, or train them)")
        self.model = YOLO(str(path))
        self.confidence, self.device, self.max_box_fraction = confidence, device, max_box_fraction

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        return _predict(
            self.model, image_rgb, self.confidence, self.device, self.max_box_fraction, _category_named
        )


def _category_named(label: str) -> Category:
    return Category(label) if label in set(Category) else Category.UNKNOWN


def _predict(model, image_rgb, confidence, device, max_box_fraction, to_category) -> list[Detection]:
    # Ultralytics expects BGR numpy arrays.
    result = model.predict(image_rgb[..., ::-1], conf=confidence, device=device, verbose=False)[0]
    height, width = image_rgb.shape[:2]
    detections = []
    for box, conf, cls in zip(
        result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist(), strict=True
    ):
        x1, y1, x2, y2 = box
        # A box covering most of the image is the floor or the robot itself, not an object.
        if (x2 - x1) * (y2 - y1) > max_box_fraction * width * height:
            continue
        label = result.names[int(cls)]
        detections.append(Detection(label, to_category(label), float(conf), (x1, y1, x2, y2)))
    return detections
