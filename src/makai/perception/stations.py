"""Find the drop-off stations (bin, laundry basket) from the ArUco marker on each one.

Markers are printed and taped vertically on the front of each station, at camera
height if possible. `solvePnP` gives the marker's position and orientation in the camera
frame and the camera model converts them to the base frame. The orientation tells which way
the station faces: the sweeping mission uses it to put its heading right at every visit.

Print markers with:  uv run python scripts/make_markers.py
"""

from __future__ import annotations

import math
from collections.abc import Mapping

import cv2
import numpy as np

from makai.contracts import Category, StationSighting
from makai.perception.geometry import CameraModel

DICTIONARY = cv2.aruco.DICT_4X4_50


class StationDetector:
    def __init__(self, camera: CameraModel, marker_ids: Mapping[int, Category], marker_size_m: float = 0.10):
        self.camera = camera
        self.marker_ids = dict(marker_ids)
        self._detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY))
        half = marker_size_m / 2.0
        # Corner order returned by OpenCV: top-left, top-right, bottom-right, bottom-left.
        self._corners_3d = np.array(
            [[-half, half, 0], [half, half, 0], [half, -half, 0], [-half, -half, 0]], dtype=np.float64
        )

    def detect(self, image_rgb: np.ndarray) -> dict[Category, StationSighting]:
        gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        corners, ids, _ = self._detector.detectMarkers(gray)
        sightings: dict[Category, StationSighting] = {}
        if ids is None:
            return sightings
        for marker_corners, marker_id in zip(corners, ids.flatten(), strict=True):
            category = self.marker_ids.get(int(marker_id))
            if category is None:
                continue
            ok, rvec, tvec = cv2.solvePnP(
                self._corners_3d,
                marker_corners.reshape(4, 2).astype(np.float64),
                self.camera.matrix,
                None,
                flags=cv2.SOLVEPNP_IPPE_SQUARE,
            )
            if ok:
                centre = self.camera.camera_to_base(tvec)
                # The marker's z axis comes out of its face, towards whoever looks at it.
                normal = cv2.Rodrigues(rvec)[0][:, 2]
                ahead = self.camera.camera_to_base(tvec.reshape(3) + 0.1 * normal) - centre
                facing = math.atan2(float(ahead[1]), float(ahead[0]))
                sightings[category] = StationSighting(category, float(centre[0]), float(centre[1]), facing)
        return sightings
