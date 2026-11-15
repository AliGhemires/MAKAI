"""ArUco-based code, tested on images rendered with the camera model (no hardware)."""

import math

import cv2
import numpy as np
import pytest

from makai.contracts import Category
from makai.perception.calibration import render_sheet, sheet_correspondences
from makai.perception.geometry import CameraModel, GroundPlane
from makai.perception.stations import DICTIONARY, StationDetector

CAMERA = CameraModel(width=640, height=480, hfov_deg=55, height_m=0.25, pitch_deg=35, x_offset_m=0.05)


def warp_into_view(texture: np.ndarray, corner_pixels: np.ndarray) -> np.ndarray:
    """Draw `texture` in the camera image so that its 4 corners land on `corner_pixels`."""
    h, w = texture.shape[:2]
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(src, corner_pixels.astype(np.float32))
    view = cv2.warpPerspective(texture, matrix, (CAMERA.width, CAMERA.height), borderValue=128)
    return cv2.cvtColor(view, cv2.COLOR_GRAY2RGB)


def test_ground_calibration_from_rendered_sheets():
    truth = CAMERA.ground_plane()
    sheet = render_sheet(pixels_per_m=2000)
    pixels, ground = [], []
    for distance in (0.15, 0.40):
        # Sheet corners on the floor: (along the axis, to the left), from the page's top-left.
        floor = [(distance + 0.297, 0.105), (distance + 0.297, -0.105), (distance, -0.105), (distance, 0.105)]
        image = warp_into_view(sheet, np.array([truth.ground_to_pixel(x, y) for x, y in floor]))
        px, gr = sheet_correspondences(image, distance)
        assert len(px) >= 16, "at least 4 of the 6 markers must be found"
        pixels.append(px)
        ground.append(gr)
    fitted = GroundPlane.fit(np.concatenate(pixels), np.concatenate(ground))
    for x, y in [(0.22, 0.0), (0.5, 0.15), (0.9, -0.2)]:
        assert fitted.pixel_to_ground(*truth.ground_to_pixel(x, y)) == pytest.approx((x, y), abs=0.01)


@pytest.mark.parametrize("position", [(0.7, 0.0), (1.0, 0.2), (1.1, -0.25)])
def test_station_marker_is_located_in_the_base_frame(position):
    x, y = position
    size, z = 0.10, 0.07  # marker side and height of its centre: taped right above the floor
    # Vertical marker facing the robot, margin included (ArUco needs the white border).
    margin = 0.02
    half = size / 2 + margin
    corners_3d = [
        (x, y + half, z + half),
        (x, y - half, z + half),
        (x, y - half, z - half),
        (x, y + half, z - half),
    ]
    side = 400
    texture = np.full((side, side), 255, dtype=np.uint8)
    border = int(side * margin / (2 * half))
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(DICTIONARY), 1, side - 2 * border
    )
    texture[border : side - border, border : side - border] = marker
    # A camera that looks further ahead than the floor-calibration one, so the marker is in view.
    camera = CameraModel(width=640, height=480, hfov_deg=46, height_m=0.20, pitch_deg=20, x_offset_m=0.05)
    image = warp_into_view(texture, np.array([camera.project(np.array(c)) for c in corners_3d]))

    sightings = StationDetector(camera, {0: Category.CLOTHING, 1: Category.TRASH}, size).detect(image)
    assert set(sightings) == {Category.TRASH}
    assert (sightings[Category.TRASH].x_m, sightings[Category.TRASH].y_m) == pytest.approx((x, y), abs=0.05)
    # The marker faces the robot squarely: its front points back along -x.
    assert abs(abs(sightings[Category.TRASH].facing_rad) - math.pi) < 0.2


@pytest.mark.parametrize("turned_deg", [-30, -15, 15, 30])
def test_station_marker_tells_which_way_the_station_faces(turned_deg):
    """A marker turned about the vertical: the sweeping mission reads its heading from it."""
    x, y, size, z, margin = 0.55, 0.0, 0.10, 0.12, 0.02
    half = size / 2 + margin
    facing = math.pi + math.radians(turned_deg)  # where its front points, in the base frame
    right = (-math.sin(facing), math.cos(facing))  # the marker's right-hand side, seen from its front
    corners_3d = [
        (x + sx * half * right[0], y + sx * half * right[1], z + sz * half)
        for sx, sz in ((-1, 1), (1, 1), (1, -1), (-1, -1))
    ]
    side = 400
    texture = np.full((side, side), 255, dtype=np.uint8)
    border = int(side * margin / (2 * half))
    marker = cv2.aruco.generateImageMarker(
        cv2.aruco.getPredefinedDictionary(DICTIONARY), 1, side - 2 * border
    )
    texture[border : side - border, border : side - border] = marker
    camera = CameraModel(width=640, height=480, hfov_deg=46, height_m=0.20, pitch_deg=20, x_offset_m=0.05)
    image = warp_into_view(texture, np.array([camera.project(np.array(c)) for c in corners_3d]))

    sighting = StationDetector(camera, {1: Category.TRASH}, size).detect(image)[Category.TRASH]
    error = (sighting.facing_rad - facing + math.pi) % (2 * math.pi) - math.pi
    assert abs(math.degrees(error)) < 6
    assert (sighting.x_m, sighting.y_m) == pytest.approx((x, y), abs=0.03)


def test_project_is_the_inverse_of_camera_to_base():
    point_cam = np.array([0.1, -0.05, 0.9])
    u, v = CAMERA.project(CAMERA.camera_to_base(point_cam))
    expected = CAMERA.matrix @ point_cam
    assert (u, v) == pytest.approx((expected[0] / expected[2], expected[1] / expected[2]))
