import json
import math
import threading
import time
import urllib.error
import urllib.request

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Observation
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import BaseGeometry
from makai.robot.manual import OWNER_TIMEOUT_S, DriveLimits, DriveLoop, ManualDriver
from makai.sim.world import SimRobot, SimWorld

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
LIMITS = DriveLimits.from_config(COMMITTED["teleop"]["drive"])
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
DT = 0.02  # 50 Hz, as DriveLoop


def run(driver, start, seconds):
    """Step the driver at 50 Hz; returns the velocities and the time reached."""
    out, t = [], start
    for _ in range(round(seconds / DT)):
        t += DT
        out.append(driver.step(t))
    return out, t


def test_config_limits_are_loaded():
    assert LIMITS.max_lin_m_s == 0.25 and LIMITS.max_ang_deg_s == 90
    assert 0 < LIMITS.accel_m_s2 < LIMITS.decel_m_s2
    assert 0 < LIMITS.deadman_s < OWNER_TIMEOUT_S


def test_full_stick_ramps_up_without_jumps_then_holds_top_speed():
    driver = ManualDriver(LIMITS)
    driver.step(0.0)
    vels, t = [], 0.0
    for _ in range(50):  # keep sending, as the page does
        driver.command("a", 1, 0, 0, 1.0, t)
        t += DT
        vels.append(driver.step(t).x)
    steps = [b - a for a, b in zip([0.0, *vels], vels, strict=False)]
    assert max(steps) <= LIMITS.accel_m_s2 * DT + 1e-9
    assert vels[0] > 0
    assert vels[-1] == pytest.approx(LIMITS.max_lin_m_s)
    assert max(vels) <= LIMITS.max_lin_m_s + 1e-9


def test_releasing_the_stick_brakes_harder_than_it_accelerates():
    driver = ManualDriver(LIMITS)
    t = 0.0
    for _ in range(60):
        driver.command("a", 1, 0, 0, 1.0, t)
        t += DT
        driver.step(t)
    driver.command("a", 0, 0, 0, 1.0, t)
    t += DT
    first = driver.step(t).x
    assert LIMITS.max_lin_m_s - first == pytest.approx(LIMITS.decel_m_s2 * DT)
    vels = []
    for _ in range(20):
        driver.command("a", 0, 0, 0, 1.0, t)
        t += DT
        vels.append(driver.step(t).x)
    assert vels[-1] == 0.0
    assert all(v >= 0 for v in vels)  # no overshoot backwards


def test_diagonal_stays_diagonal_while_speeding_up():
    driver = ManualDriver(LIMITS)
    t = 0.0
    driver.step(t)
    for _ in range(30):
        driver.command("a", 0.6, 0.8, 0, 1.0, t)
        t += DT
        v = driver.step(t)
        assert v.y == pytest.approx(v.x * 0.8 / 0.6)


def test_turning_is_rate_limited_too():
    driver = ManualDriver(LIMITS)
    driver.step(0.0)
    driver.command("a", 0, 0, 1, 1.0, 0.0)
    v = driver.step(DT)
    assert v.theta == pytest.approx(math.radians(LIMITS.ang_accel_deg_s2) * DT)
    vels, _ = run(driver, DT, 0.3)
    assert vels[-1].theta > 0


def test_speed_scales_the_maximum():
    driver = ManualDriver(LIMITS)
    driver.step(0.0)
    t = 0.0
    for _ in range(60):
        driver.command("a", 1, 0, -1, 0.5, t)
        t += DT
        v = driver.step(t)
    assert v.x == pytest.approx(LIMITS.max_lin_m_s * 0.5)
    assert v.theta == pytest.approx(-math.radians(LIMITS.max_ang_deg_s) * 0.5)


def test_dead_mans_switch_brakes_when_the_page_goes_quiet():
    driver = ManualDriver(LIMITS)
    t = 0.0
    for _ in range(60):
        driver.command("a", 1, 0, 0, 1.0, t)
        t += DT
        driver.step(t)
    # Page closed: no more commands.
    vels, _ = run(driver, t, LIMITS.deadman_s - 2 * DT)
    assert vels[-1].x == pytest.approx(LIMITS.max_lin_m_s)  # within the grace period: keep going
    vels, _ = run(driver, t + LIMITS.deadman_s - 2 * DT, 1.0)
    assert vels[-1].is_zero()


def test_emergency_stop_is_immediate_and_latched_until_released():
    driver = ManualDriver(LIMITS)
    t = 0.0
    for _ in range(60):
        driver.command("a", 1, 0, 0, 1.0, t)
        t += DT
        driver.step(t)
    driver.emergency_stop()
    t += DT
    assert driver.step(t).is_zero()
    driver.command("a", 1, 0, 0, 1.0, t)
    t += DT
    assert driver.step(t).is_zero()
    assert driver.status("a", t)["estop"]
    driver.release()
    t += DT
    assert driver.step(t).is_zero()  # still: waits for the next input
    driver.command("a", 1, 0, 0, 1.0, t)
    t += DT
    assert driver.step(t).x > 0


def test_one_driver_at_a_time():
    driver = ManualDriver(LIMITS)
    assert driver.command("a", 1, 0, 0, 1.0, 0.0, label="iPhone")
    assert not driver.command("b", -1, 0, 0, 1.0, 0.1)  # ignored
    assert driver.status("b", 0.1) == {"estop": False, "you_drive": False, "driver": "iPhone"}
    assert driver.status("a", 0.1)["you_drive"]
    assert driver.command("a", 0, 0, 0, 1.0, 0.2)  # the driver idles: still the driver
    assert not driver.command("b", -1, 0, 0, 1.0, 0.3)
    assert driver.command("b", -1, 0, 0, 1.0, 0.4, takeover=True, label="Mac")
    assert not driver.command("a", 1, 0, 0, 1.0, 0.5)
    assert driver.status("a", 0.5)["driver"] == "Mac"


def test_a_silent_driver_frees_the_wheels():
    driver = ManualDriver(LIMITS)
    assert driver.command("a", 1, 0, 0, 1.0, 0.0)
    assert driver.command("b", 0, 1, 0, 1.0, OWNER_TIMEOUT_S + 0.1)


def test_an_idle_page_does_not_claim_the_wheels():
    driver = ManualDriver(LIMITS)
    assert not driver.command("watcher", 0, 0, 0, 1.0, 0.0)
    assert driver.status("watcher", 0.0)["driver"] is None
    assert driver.command("a", 1, 0, 0, 1.0, 0.1)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "fast", None, [1]])
def test_garbage_input_is_treated_as_zero(bad):
    driver = ManualDriver(LIMITS)
    driver.step(0.0)
    driver.command("a", bad, 0, bad, bad, 0.0, takeover=True)
    v = driver.step(DT)
    assert v.is_zero() and all(math.isfinite(c) for c in (v.x, v.y, v.theta))


def test_out_of_range_input_is_clipped():
    driver = ManualDriver(LIMITS)
    t = 0.0
    for _ in range(80):
        driver.command("a", 30, 40, 9, 7, t)
        t += DT
        v = driver.step(t)
    assert math.hypot(v.x, v.y) == pytest.approx(LIMITS.max_lin_m_s)
    assert v.theta == pytest.approx(math.radians(LIMITS.max_ang_deg_s))


class RecordingRobot:
    def __init__(self):
        self.sent, self.stopped, self.fail = [], 0, None

    def drive(self, velocity):
        if self.fail:
            raise self.fail
        self.sent.append(velocity)

    def get_observation(self):
        return Observation(stamp=0.0, base_velocity=self.sent[-1] if self.sent else BaseVelocity())

    def stop(self):
        self.stopped += 1

    def battery_voltage(self):
        return 12.3


def test_loop_sends_every_tick_and_reports_telemetry():
    robot, driver = RecordingRobot(), ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)
    driver.command("a", 1, 0, 0, 1.0, 0.0)
    for i in range(1, 6):
        loop.tick(i * DT)
    assert len(robot.sent) == 5 and robot.sent[-1].x > 0
    snap = loop.snapshot()
    assert snap["cmd"]["x"] == pytest.approx(robot.sent[-1].x, abs=1e-4)
    assert snap["meas"] is not None and snap["battery_v"] == 12.3
    assert snap["wheels"]["back"] == 0 and snap["wheels"]["left"] == -snap["wheels"]["right"]
    assert snap["error"] is None


def test_loop_survives_robot_errors_and_recovers():
    robot, driver = RecordingRobot(), ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)
    robot.fail = PermissionError("Access is denied")
    loop.tick(0.0)
    assert "Access is denied" in loop.snapshot()["error"]
    robot.fail = None
    loop.tick(DT)
    assert loop.snapshot()["error"] is None


def test_loop_tracks_odometry_in_simulation_and_stops_the_robot():
    world = SimWorld()
    robot, driver = SimRobot(world, dt=0.1), ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)
    t = 0.0
    for _ in range(150):  # 3 s forward
        driver.command("a", 1, 0, 0, 1.0, t)
        loop.tick(t)
        t += DT
    pose = loop.snapshot()["pose"]
    assert pose["x"] > 0.3 and abs(pose["y"]) < 1e-6
    loop.reset_odometry()
    snap = loop.snapshot()
    assert snap["pose"]["x"] == 0 and snap["odometry_epoch"] == 1
    loop.stop()
    assert robot.get_observation().base_velocity.is_zero()


@pytest.fixture
def server():
    robot, driver = RecordingRobot(), ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)
    info = {
        "link": "test",
        "serial_port": None,
        "limits": {"max_lin_m_s": 0.25},
        "wheels": ["left", "back", "right"],
    }
    srv = DriveServer(("127.0.0.1", 0), loop, driver, info)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, path, body=None, raw=None):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as res:
        payload = res.read()
        return json.loads(payload) if res.headers["Content-Type"] == "application/json" else payload.decode()


def test_server_serves_the_page_and_its_info(server):
    page = call(server, "/")
    assert "<title>MAKAI drive</title>" in page and "/api/drive" in page
    assert call(server, "/api/info")["link"] == "test"
    assert call(server, "/api/state")["you_drive"] is False


def test_server_drives_stops_and_releases(server):
    state = call(
        server, "/api/drive", {"client": "page1", "label": "Mac", "x": 1, "y": 0, "turn": 0, "speed": 1}
    )
    assert state["you_drive"] and not state["estop"]
    assert call(server, "/api/drive", {"client": "page2", "x": -1, "speed": 1})["driver"] == "Mac"
    assert call(server, "/api/stop", {"client": "page2"})["estop"]  # anyone can stop the robot
    assert not call(server, "/api/release", {"client": "page1"})["estop"]
    assert call(server, "/api/reset_odometry", {"client": "page1"})["odometry_epoch"] == 1


def test_server_rejects_bad_requests(server):
    for raw in (b"not json", b"[1, 2]", b"x" * 5000):
        with pytest.raises(urllib.error.HTTPError) as err:
            call(server, "/api/drive", raw=raw)
        assert err.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as err:
        call(server, "/api/drive", {"x": 1})  # no client id
    assert err.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as err:
        call(server, "/api/nothing", {"client": "a"})
    assert err.value.code == 404


def test_server_turns_nan_into_zero(server):
    raw = b'{"client": "a", "x": NaN, "y": Infinity, "turn": 0, "speed": 1, "takeover": true}'
    assert call(server, "/api/drive", raw=raw)["you_drive"]
    for _ in range(10):
        now = time.monotonic()
        assert server.driver.step(now).is_zero()
