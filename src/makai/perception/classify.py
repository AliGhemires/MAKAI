"""Is the object lying in front of us clothing, or something else?

That is the only question the mission needs answered: laundry basket, or bin.

- `UniformityClassifier`: fabric looks plain and matte, packaging looks printed and
  contrasted. Two numbers, no model, no download. Tuned on one black sock and one drink can
  (14 Nov): expect to retune it for other objects, and do not expect it to tell a white sock
  from a paper ball.
- `ClipClassifier`: compares the crop with sentences, using CLIP (no training). Needs the
  `perception` extra and a 340 MB download on first use.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from makai.contracts import Category
from makai.perception.floor import FloorColor


class UniformityClassifier:
    def __init__(
        self,
        floor: FloorColor | None = None,
        max_edge_density: float = 0.15,  # share of the object's pixels that sit on an edge
        max_contrast: float = 40.0,  # standard deviation of brightness inside the object (0..255)
        min_object_px: int = 45,  # smaller than this in the image: too far to tell, no answer
        size: int = 128,  # objects larger than this are shrunk first, so distance matters less
    ):
        self.floor = floor or FloorColor()
        self.max_edge_density, self.max_contrast = max_edge_density, max_contrast
        self.min_object_px, self.size = min_object_px, size

    def features(self, crop_rgb: np.ndarray) -> tuple[float, float] | None:
        """(edge density, brightness contrast) of the object in the crop, or None if too small.

        Measured 14 Nov: reliable down to about 45 px; below that the outline dominates and a
        sock reads like a can.
        """
        rows, cols = np.nonzero(~self.floor.mask(crop_rgb))
        if rows.size == 0 or max(np.ptp(rows), np.ptp(cols)) + 1 < self.min_object_px:
            return None
        height, width = crop_rgb.shape[:2]
        scale = min(1.0, self.size / max(height, width))
        if scale < 1.0:
            new_size = (max(8, round(width * scale)), max(8, round(height * scale)))
            crop_rgb = cv2.resize(crop_rgb, new_size, interpolation=cv2.INTER_AREA)
        # The crop includes some carpet around the object: measure the object only, outline excluded.
        inside = cv2.erode((~self.floor.mask(crop_rgb)).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        if not inside.any():
            return None
        gray = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2GRAY)
        edge_density = float(cv2.Canny(gray, 60, 150)[inside].mean() / 255.0)
        return edge_density, float(gray[inside].std())

    def classify(self, crop_rgb: np.ndarray) -> tuple[Category, float]:
        features = self.features(crop_rgb)
        if features is None:
            return Category.UNKNOWN, 0.0
        # How far each measure is from its limit: below 1 on both means plain and matte.
        ratio = max(features[0] / self.max_edge_density, features[1] / self.max_contrast)
        if ratio <= 1.0:
            return Category.CLOTHING, min(1.0, 0.5 + 0.5 * (1.0 - ratio))
        return Category.TRASH, min(1.0, 0.5 + 0.5 * (ratio - 1.0))


class ClipClassifier:
    def __init__(
        self,
        clothing: Sequence[str],
        other: Sequence[str],
        model: str = "ViT-B/32",
        device: str | None = None,
        threshold: float = 0.5,
    ):
        import clip
        import torch

        self._torch = torch
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model, self.preprocess = clip.load(model, device=self.device)
        self.threshold, self.n_clothing = threshold, len(clothing)
        with torch.no_grad():
            text = self.model.encode_text(clip.tokenize([*clothing, *other]).to(self.device)).float()
        self.text = text / text.norm(dim=-1, keepdim=True)

    def probability_clothing(self, crop_rgb: np.ndarray) -> float:
        from PIL import Image

        torch = self._torch
        with torch.no_grad():
            pixels = self.preprocess(Image.fromarray(crop_rgb)).unsqueeze(0).to(self.device)
            image = self.model.encode_image(pixels).float()
            image = image / image.norm(dim=-1, keepdim=True)
            probabilities = (100.0 * image @ self.text.T).softmax(dim=-1)[0]
        return float(probabilities[: self.n_clothing].sum())

    def classify(self, crop_rgb: np.ndarray) -> tuple[Category, float]:
        p = self.probability_clothing(crop_rgb)
        return (Category.CLOTHING, p) if p >= self.threshold else (Category.TRASH, 1.0 - p)
