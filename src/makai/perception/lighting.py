"""Artificial re-lighting of images: to stress-test a detector and to augment its training data.

Uniform changes (darker, warmer, washed out...) plus hard and soft shadows. Real lighting is
messier than this, so photos taken under the real lighting remain the test that counts.
"""

from __future__ import annotations

import cv2
import numpy as np


def scale(image: np.ndarray, r: float = 1.0, g: float = 1.0, b: float = 1.0) -> np.ndarray:
    return np.clip(image.astype(np.float32) * np.array([r, g, b], dtype=np.float32), 0, 255).astype(np.uint8)


def noise(image: np.ndarray, sigma: float, seed: int = 0) -> np.ndarray:
    grain = np.random.default_rng(seed).normal(0.0, sigma, image.shape)
    return np.clip(image.astype(np.float32) + grain, 0, 255).astype(np.uint8)


def gamma(image: np.ndarray, value: float) -> np.ndarray:
    return (255.0 * (image.astype(np.float32) / 255.0) ** value).astype(np.uint8)


def desaturate(image: np.ndarray, keep: float) -> np.ndarray:
    gray = image.astype(np.float32).mean(axis=2, keepdims=True)
    return np.clip(gray + keep * (image.astype(np.float32) - gray), 0, 255).astype(np.uint8)


def contrast(image: np.ndarray, factor: float) -> np.ndarray:
    return np.clip(factor * (image.astype(np.float32) - 128) + 128, 0, 255).astype(np.uint8)


def shadow(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Darken a random four-sided region, with a hard or a soft edge."""
    height, width = image.shape[:2]
    corners = np.array(
        [
            [rng.integers(-width // 2, width), rng.integers(0, height)],
            [rng.integers(0, width + width // 2), rng.integers(0, height)],
            [rng.integers(0, width + width // 2), height + 50],
            [rng.integers(-width // 2, width), height + 50],
        ],
        np.int32,
    )
    mask = np.zeros((height, width), np.float32)
    cv2.fillPoly(mask, [corners], 1.0)
    if rng.random() < 0.5:
        mask = cv2.GaussianBlur(mask, (0, 0), rng.uniform(2, 25))
    darkened = image.astype(np.float32) * (1.0 - mask[..., None] * rng.uniform(0.35, 0.8))
    return np.clip(darkened, 0, 255).astype(np.uint8)


def random_relight(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """A random plausible lighting: used to multiply training images."""
    out = shadow(image, rng) if rng.random() < 0.6 else image
    out = out.astype(np.float32) * rng.uniform(0.3, 1.5) * rng.uniform(0.75, 1.25, 3)
    out = 255.0 * (np.clip(out, 0, 255) / 255.0) ** rng.uniform(0.6, 1.6)
    if rng.random() < 0.5:
        gray = out.mean(axis=2, keepdims=True)
        out = gray + rng.uniform(0.4, 1.0) * (out - gray)
    if rng.random() < 0.4:
        out = rng.uniform(0.6, 1.0) * (out - 128) + 128
    return np.clip(out + rng.normal(0, rng.uniform(0, 8), out.shape), 0, 255).astype(np.uint8)


# Fixed lightings for the stress test (scripts/eval_lighting.py).
LIGHTINGS = {
    "very dark (x0.3)": lambda im: scale(im, 0.3, 0.3, 0.3),
    "dark (x0.5)": lambda im: scale(im, 0.5, 0.5, 0.5),
    "dim (x0.75)": lambda im: scale(im, 0.75, 0.75, 0.75),
    "bright (x1.3)": lambda im: scale(im, 1.3, 1.3, 1.3),
    "very bright (x1.6)": lambda im: scale(im, 1.6, 1.6, 1.6),
    "gamma 0.6": lambda im: gamma(im, 0.6),
    "gamma 1.6": lambda im: gamma(im, 1.6),
    "warm light": lambda im: scale(im, 1.2, 1.0, 0.7),
    "cool light": lambda im: scale(im, 0.8, 1.0, 1.25),
    "green tint": lambda im: scale(im, 0.95, 1.12, 0.95),
    "washed out": lambda im: desaturate(im, 0.5),
    "low contrast": lambda im: contrast(im, 0.6),
    "dark + noise": lambda im: noise(scale(im, 0.35, 0.35, 0.35), 8.0),
    "evening (dark, warm, noise)": lambda im: noise(scale(im, 0.6, 0.5, 0.35), 6.0),
    "cold lamp (dark, cool, noise)": lambda im: noise(scale(im, 0.45, 0.55, 0.7), 6.0),
    "hard shadow 1": lambda im: shadow(im, np.random.default_rng(11)),
    "hard shadow 2": lambda im: shadow(im, np.random.default_rng(22)),
    "hard shadow 3": lambda im: shadow(im, np.random.default_rng(33)),
}
