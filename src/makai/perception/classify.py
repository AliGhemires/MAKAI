"""Is the object lying in front of us clothing, or something else?

`ClipClassifier` compares a tight crop of the object with a few sentences describing clothing
and a few describing other things, using CLIP (no training). It answers the only question the
mission needs: laundry basket, or bin.

Needs the `perception` extra; the weights (about 340 MB) are downloaded on first use.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from makai.contracts import Category


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
