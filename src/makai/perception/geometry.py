"""Camera geometry: pixel <-> floor mapping without any depth sensor.

Objects lie on the floor and the front camera is rigidly fixed to the base, so a
single homography maps image pixels to metric (x, y) in the base frame. That is
the whole "distance estimation": no depth network needed.

Two ways to get the mapping:
- `CameraModel.ground_plane()`: from measured height / pitch / FOV. Zero calibration,
  good enough to start (a few cm of error).
- `GroundPlane.fit()`: from >= 4 floor points with known positions. This is the one
  to use for the demo (see `makai-calibrate-ground`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import yaml


class GroundPlane:
    """Homography from image pixels to floor coordinates in the base frame."""

    def __init__(self, image_to_ground: np.ndarray):
        h = np.asarray(image_to_ground, dtype=np.float64)
        if h.shape != (3, 3):
            raise ValueError(f"homography must be 3x3, got {h.shape}")
        self.image_to_ground = h / h[2, 2]
        self.ground_to_image = np.linalg.inv(self.image_to_ground)

    @classmethod
    def fit(cls, pixels: np.ndarray, ground_xy: np.ndarray) -> GroundPlane:
        """Fit from N >= 4 correspondences (pixels Nx2 -> metres Nx2)."""
        pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
        ground_xy = np.asarray(ground_xy, dtype=np.float64).reshape(-1, 2)
        if len(pixels) < 4 or len(pixels) != len(ground_xy):
            raise ValueError("need >= 4 matching pixel / ground points")
        h, _ = cv2.findHomography(pixels, ground_xy, method=0)
        if h is None:
            raise ValueError("homography fit failed (are the points collinear?)")
        return cls(h)

    def pixel_to_ground(self, u: float, v: float) -> tuple[float, float]:
        p = self.image_to_ground @ np.array([u, v, 1.0])
        return float(p[0] / p[2]), float(p[1] / p[2])

    def ground_to_pixel(self, x_m: float, y_m: float) -> tuple[float, float]:
        p = self.ground_to_image @ np.array([x_m, y_m, 1.0])
        return float(p[0] / p[2]), float(p[1] / p[2])

    def reprojection_error_m(self, pixels: np.ndarray, ground_xy: np.ndarray) -> float:
        """Mean distance (m) between fitted and measured floor points."""
        pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
        ground_xy = np.asarray(ground_xy, dtype=np.float64).reshape(-1, 2)
        pred = np.array([self.pixel_to_ground(u, v) for u, v in pixels])
        return float(np.linalg.norm(pred - ground_xy, axis=1).mean())

    def save(self, path: str | Path) -> None:
        Path(path).write_text(yaml.safe_dump({"image_to_ground": self.image_to_ground.tolist()}))

    @classmethod
    def load(cls, path: str | Path) -> GroundPlane:
        return cls(np.array(yaml.safe_load(Path(path).read_text())["image_to_ground"]))


@dataclass(frozen=True)
class CameraModel:
    """Pinhole model of a camera rigidly mounted on the base, looking forward and down."""

    width: int = 640
    height: int = 480
    hfov_deg: float = 55.0  # horizontal field of view
    height_m: float = 0.25  # lens height above the floor
    pitch_deg: float = 30.0  # tilt below the horizontal
    x_offset_m: float = 0.0  # lens position ahead of the base centre

    @property
    def focal_px(self) -> float:
        return (self.width / 2.0) / math.tan(math.radians(self.hfov_deg) / 2.0)

    @property
    def matrix(self) -> np.ndarray:
        f = self.focal_px
        return np.array([[f, 0.0, self.width / 2.0], [0.0, f, self.height / 2.0], [0.0, 0.0, 1.0]])

    def camera_to_base(self, point_cam: np.ndarray) -> np.ndarray:
        """OpenCV camera frame (x right, y down, z forward) -> base frame (x fwd, y left, z up)."""
        xc, yc, zc = (float(c) for c in np.asarray(point_cam).reshape(3))
        sp, cp = math.sin(math.radians(self.pitch_deg)), math.cos(math.radians(self.pitch_deg))
        return np.array(
            [
                self.x_offset_m - sp * yc + cp * zc,
                -xc,
                self.height_m - cp * yc - sp * zc,
            ]
        )

    def project(self, point_base: np.ndarray) -> tuple[float, float]:
        """Base-frame 3D point -> pixel. Inverse of `camera_to_base` followed by the pinhole model."""
        x, y, z = (float(c) for c in np.asarray(point_base).reshape(3))
        sp, cp = math.sin(math.radians(self.pitch_deg)), math.cos(math.radians(self.pitch_deg))
        dx, dz = x - self.x_offset_m, z - self.height_m
        xc, yc, zc = -y, -sp * dx - cp * dz, cp * dx - sp * dz
        f = self.focal_px
        return f * xc / zc + self.width / 2.0, f * yc / zc + self.height / 2.0

    def ground_plane(self) -> GroundPlane:
        sp, cp = math.sin(math.radians(self.pitch_deg)), math.cos(math.radians(self.pitch_deg))
        # Rows give camera-frame (Xc, Yc, Zc) of the floor point (x, y, 1).
        ground_to_cam = np.array(
            [
                [0.0, -1.0, 0.0],
                [-sp, 0.0, sp * self.x_offset_m + cp * self.height_m],
                [cp, 0.0, -cp * self.x_offset_m + sp * self.height_m],
            ]
        )
        return GroundPlane(np.linalg.inv(self.matrix @ ground_to_cam))
