import threading
import time
import urllib.error
import urllib.request

import cv2
import numpy as np
import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Observation
from makai.robot.cameras import STALE_S, CameraCapture, CameraHub, SimCamera, render_floor
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import BaseGeometry
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
LIMITS = DriveLimits.from_config(COMMITTED["teleop"]["drive"])


def red_image(rgb):
    img = np.zeros((48, 64, 3), np.uint8)
    img[:, :, 0 if rgb else 2] = 255  # pure red, in RGB or in BGR
    return img


def decoded(jpeg):
    return cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)  # BGR


@pytest.mark.parametrize("rgb", [True, False])
def test_images_keep_their_colours_whatever_their_channel_order(rgb):
    hub = CameraHub()
    hub.put("front", red_image(rgb), rgb=rgb)
    blue, green, red = decoded(hub.jpeg("front")[1]).mean(axis=(0, 1))
    assert red > 200 and blue < 50 and green < 50


def test_each_image_is_encoded_once_for_all_viewers():
    hub = CameraHub()
    hub.put("front", red_image(True), rgb=True)
    first, second = hub.jpeg("front"), hub.jpeg("front")
    assert first[0] == second[0] == 1 and first[1] is second[1]
    hub.put("front", red_image(True), rgb=True)
    assert hub.jpeg("front")[0] == 2


def test_waiting_for_a_new_image():
    hub = CameraHub()
    hub.expect("front")
    assert hub.jpeg("front") is None
    assert hub.wait_jpeg("front", 0, timeout=0.05) is None
    threading.Timer(0.05, lambda: hub.put("front", red_image(True), rgb=True)).start()
    frame = hub.wait_jpeg("front", 0, timeout=2.0)
    assert frame is not None and frame[0] == 1


def test_status_says_waiting_live_or_lost():
    now = [100.0]
    hub = CameraHub(clock=lambda: now[0])
    hub.expect("wrist", "/dev/video2")
    assert hub.status()["wrist"]["error"] == "waiting for the first image"
    for _ in range(11):
        hub.put("wrist", red_image(True), rgb=True)
        now[0] += 0.1
    status = hub.status()["wrist"]
    assert status["ok"] and status["fps"] == pytest.approx(10, abs=0.5)
    assert (status["width"], status["height"], status["source"]) == (64, 48, "/dev/video2")
    now[0] += STALE_S + 1
    assert not hub.status()["wrist"]["ok"] and "no new image" in hub.status()["wrist"]["error"]
    hub.fail("wrist", "unplugged")
    assert hub.status()["wrist"]["error"] == "unplugged"


def test_a_missing_camera_is_reported_not_fatal():
    hub = CameraHub()
    capture = CameraCapture(hub, "wrist", "/dev/does-not-exist", 640, 480)
    capture.start()
    deadline = time.monotonic() + 5
    while "cannot open" not in (hub.status()["wrist"]["error"] or "") and time.monotonic() < deadline:
        time.sleep(0.05)
    capture.stop()
    assert "cannot open /dev/does-not-exist" in hub.status()["wrist"]["error"]


def test_simulated_camera_shows_the_floor_moving():
    a, b = render_floor("front", 0, 0, 0), render_floor("front", 0.3, 0, 0.5)
    assert a.shape == (480, 640, 3) and not np.array_equal(a, b)
    hub = CameraHub()
    sim = SimCamera(hub, "front", lambda: (0.0, 0.0, 0.0), fps=50)
    sim.start()
    assert hub.wait_jpeg("front", 0, timeout=2.0) is not None
    sim.stop()


class CameraRobot:
    """Through the host: images and arm angles come with each observation."""

    def drive(self, velocity): ...

    def stop(self): ...

    def get_observation(self):
        return Observation(
            stamp=0.0,
            images={"front": red_image(True)},
            arm={"arm_gripper.pos": 42.0, "arm_elbow_flex.pos": -80.0},
            base_velocity=BaseVelocity(),
        )


def test_the_loop_passes_host_images_and_arm_angles_to_the_page():
    hub = CameraHub()
    loop = DriveLoop(CameraRobot(), ManualDriver(LIMITS), GEOMETRY, cameras=hub)
    loop.tick(0.0)
    snap = loop.snapshot()
    assert snap["arm"] == {"gripper": 42.0, "elbow_flex": -80.0}
    assert snap["cameras"]["front"]["ok"]
    _, _, red = decoded(hub.jpeg("front")[1]).mean(axis=(0, 1))
    assert red > 200


@pytest.fixture
def server():
    hub = CameraHub()
    hub.expect("front")
    hub.expect("wrist")
    loop = DriveLoop(CameraRobot(), ManualDriver(LIMITS), GEOMETRY)
    srv = DriveServer(("127.0.0.1", 0), loop, loop.driver, {"link": "test"}, hub)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def url(srv, path):
    return f"http://127.0.0.1:{srv.server_address[1]}{path}"


def test_server_streams_a_camera_as_mjpeg(server):
    stop = threading.Event()

    def feed():
        while not stop.wait(0.02):
            server.cameras.put("front", red_image(True), rgb=True)

    threading.Thread(target=feed, daemon=True).start()
    try:
        with urllib.request.urlopen(url(server, "/api/camera/front.mjpg?fps=20"), timeout=5) as res:
            assert res.headers["Content-Type"] == "multipart/x-mixed-replace; boundary=frame"
            data = b""
            while data.count(b"--frame") < 3:
                data += res.read(512)
        part = data.split(b"--frame")[1]
        head, body = part.split(b"\r\n\r\n", 1)
        assert b"Content-Type: image/jpeg" in head and body.startswith(b"\xff\xd8")  # a JPEG
    finally:
        stop.set()


def test_server_gives_the_latest_image_and_explains_missing_ones(server):
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(url(server, "/api/camera/wrist.jpg"), timeout=5)
    assert err.value.code == 503
    with pytest.raises(urllib.error.HTTPError) as err:
        urllib.request.urlopen(url(server, "/api/camera/side.jpg"), timeout=5)
    assert err.value.code == 404
    server.cameras.put("front", red_image(True), rgb=True)
    with urllib.request.urlopen(url(server, "/api/camera/front.jpg?download=1"), timeout=5) as res:
        assert res.headers["Content-Type"] == "image/jpeg"
        assert 'filename="front_' in res.headers["Content-Disposition"]
        assert res.read().startswith(b"\xff\xd8")
