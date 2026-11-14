"""Find things lying on the floor in the front camera image.

`OpenVocabDetector` wraps an Ultralytics open-vocabulary model (YOLOE / YOLO-World):
you give it words, it finds those things, no training needed. If recall is not good
enough in the arena, fine-tune a small YOLO on our own images and point `model` at
the resulting weights (see docs/workstreams/WS2_perception.md): the code is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

import numpy as np

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
        # Ultralytics expects BGR numpy arrays.
        result = self.model.predict(
            image_rgb[..., ::-1], conf=self.confidence, device=self.device, verbose=False
        )[0]
        height, width = image_rgb.shape[:2]
        detections = []
        for box, conf, cls in zip(
            result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), result.boxes.cls.tolist(), strict=True
        ):
            x1, y1, x2, y2 = box
            # A box covering most of the image is the floor or the robot itself, not an object.
            if (x2 - x1) * (y2 - y1) > self.max_box_fraction * width * height:
                continue
            label = result.names[int(cls)]
            detections.append(
                Detection(label, category_of(label, self.prompts), float(conf), (x1, y1, x2, y2))
            )
        return detections
