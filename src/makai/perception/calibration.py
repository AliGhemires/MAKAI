"""Ground-plane calibration from a printed sheet of ArUco markers laid on the floor.

No clicking, no GUI: put the sheet flat in front of the robot, centred on its axis,
long side pointing away, and measure the distance from the base centre to the sheet's
near edge. Every detected marker corner is a (pixel, floor position) pair.
"""

from __future__ import annotations

import cv2
import numpy as np

from makai.perception.stations import DICTIONARY

A4_M = (0.210, 0.297)  # width (across the robot axis), length (along it)
MARKER_SIZE_M = 0.06
SHEET_IDS = (10, 11, 12, 13, 14, 15)
# Marker centres in the sheet frame: (along the axis from the near edge, to the left of the axis).
_CENTRES = [(along, left) for along in (0.050, 0.1485, 0.247) for left in (0.055, -0.055)]


def sheet_layout(scale: float = 1.0) -> dict[int, np.ndarray]:
    """Marker id -> 4x2 corner positions (along, left) in metres, in OpenCV corner order.

    `scale` = measured printed marker side / 60 mm, if the printer rescaled the page.
    """
    half = MARKER_SIZE_M / 2.0
    layout = {}
    for marker_id, (along, left) in zip(SHEET_IDS, _CENTRES, strict=True):
        # Seen from the robot, a marker's top-left corner is the far-left one.
        corners = [
            (along + half, left + half),
            (along + half, left - half),
            (along - half, left - half),
            (along - half, left + half),
        ]
        layout[marker_id] = np.array(corners) * scale
    return layout


def render_sheet(pixels_per_m: float = 300 / 0.0254) -> np.ndarray:
    """The printable A4 sheet (portrait, 300 dpi by default). Bottom of the page = near edge."""
    width, height = (int(round(side * pixels_per_m)) for side in A4_M)
    page = np.full((height, width), 255, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    side = int(round(MARKER_SIZE_M * pixels_per_m))
    for marker_id, (along, left) in zip(SHEET_IDS, _CENTRES, strict=True):
        cx, cy = width / 2.0 - left * pixels_per_m, height - along * pixels_per_m
        x0, y0 = int(round(cx - side / 2)), int(round(cy - side / 2))
        page[y0 : y0 + side, x0 : x0 + side] = cv2.aruco.generateImageMarker(dictionary, marker_id, side)
    cv2.putText(
        page,
        "MAKAI ground calibration - this edge towards the robot",
        (int(0.02 * width), height - int(0.004 * pixels_per_m)),
        cv2.FONT_HERSHEY_SIMPLEX,
        width / 2600,
        0,
        2,
    )
    return page


def sheet_correspondences(
    image_rgb: np.ndarray, near_edge_distance_m: float, scale: float = 1.0
) -> tuple[np.ndarray, np.ndarray]:
    """Detect the sheet and return matching (pixels Nx2, floor points Nx2 in the base frame)."""
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY))
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY))
    layout = sheet_layout(scale)
    pixels, ground = [], []
    for marker_corners, marker_id in zip(corners, [] if ids is None else ids.flatten(), strict=True):
        if int(marker_id) in layout:
            pixels.append(marker_corners.reshape(4, 2))
            ground.append(layout[int(marker_id)] + np.array([near_edge_distance_m, 0.0]))
    if not pixels:
        return np.empty((0, 2)), np.empty((0, 2))
    return np.concatenate(pixels), np.concatenate(ground)
