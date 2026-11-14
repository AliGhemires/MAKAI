import numpy as np
import pytest

from makai.perception.geometry import CameraModel, GroundPlane


def test_camera_model_roundtrip():
    plane = CameraModel(height_m=0.25, pitch_deg=35, hfov_deg=55).ground_plane()
    for x, y in [(0.2, 0.0), (0.5, 0.1), (1.0, -0.3)]:
        u, v = plane.ground_to_pixel(x, y)
        assert plane.pixel_to_ground(u, v) == pytest.approx((x, y), abs=1e-9)


def test_camera_model_is_geometrically_sane():
    cam = CameraModel(width=640, height=480, height_m=0.25, pitch_deg=35)
    plane = cam.ground_plane()
    # A point straight ahead projects on the vertical centre line...
    u_near, v_near = plane.ground_to_pixel(0.25, 0.0)
    u_far, v_far = plane.ground_to_pixel(1.0, 0.0)
    assert u_near == pytest.approx(320) and u_far == pytest.approx(320)
    # ...nearer points are lower in the image, and a point on the left is left of centre.
    assert v_near > v_far
    assert plane.ground_to_pixel(0.5, 0.2)[0] < 320
    # The optical axis hits the floor at height / tan(pitch).
    x, y = plane.pixel_to_ground(320, 240)
    assert x == pytest.approx(0.25 / np.tan(np.radians(35)), rel=1e-6) and y == pytest.approx(0)


def test_fit_recovers_plane_from_floor_points():
    truth = CameraModel(height_m=0.22, pitch_deg=40, x_offset_m=0.05).ground_plane()
    ground = np.array([[0.2, -0.1], [0.2, 0.1], [0.5, -0.2], [0.5, 0.2], [0.8, 0.0], [0.35, 0.05]])
    pixels = np.array([truth.ground_to_pixel(x, y) for x, y in ground])
    fitted = GroundPlane.fit(pixels, ground)
    assert fitted.reprojection_error_m(pixels, ground) < 1e-6
    assert fitted.pixel_to_ground(*truth.ground_to_pixel(0.6, -0.1)) == pytest.approx((0.6, -0.1), abs=1e-6)


def test_save_and_load(tmp_path):
    plane = CameraModel().ground_plane()
    plane.save(tmp_path / "ground.yaml")
    loaded = GroundPlane.load(tmp_path / "ground.yaml")
    assert np.allclose(loaded.image_to_ground, plane.image_to_ground)


def test_camera_to_base_matches_ground_plane():
    cam = CameraModel(height_m=0.25, pitch_deg=35, x_offset_m=0.04)
    u, v = cam.ground_plane().ground_to_pixel(0.6, 0.15)
    # Back-project the pixel as a ray and intersect it with the floor (z = 0).
    ray = np.linalg.inv(cam.matrix) @ np.array([u, v, 1.0])
    origin = cam.camera_to_base(np.zeros(3))
    direction = cam.camera_to_base(ray) - origin
    hit = origin + direction * (-origin[2] / direction[2])
    assert hit[:2] == pytest.approx((0.6, 0.15), abs=1e-9)
