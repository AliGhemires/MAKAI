"""The console: a mission run on the control page's own loop, and the routes that drive it."""

import json
import threading
import time
import urllib.error
import urllib.request

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Category
from makai.navigation.coverage import Room, snake_waypoints
from makai.orchestrator.mission import MissionConfig
from makai.orchestrator.sweep import Station, SweepConfig, SweepMission
from makai.robot.autopilot import MissionRunner
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import BaseGeometry
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver
from makai.sim.world import SimDrop, SimPerception, SimPick, SimRobot, sweep_world

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
LIMITS = DriveLimits.from_config(COMMITTED["teleop"]["drive"])
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
SWEEP = SweepConfig(
    room=Room(length_m=2.4, width_m=1.8),
    stations={Category.TRASH: Station(-0.35, 0.0), Category.CLOTHING: Station(-0.35, 0.7, 0.0, 0.7)},
)


def make(build=None):
    """A control loop on a simulated robot, and a runner for the sweeping mission on it."""
    world = sweep_world()
    robot, driver = SimRobot(world), ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)

    def default(tap):
        return SweepMission(
            tap, SimPerception(world, station_max_range_m=1.2, max_range_m=1.5), SimPick(world), SimDrop(world),
            MissionConfig(), SWEEP,
        )  # fmt: skip

    plan = {
        "room": {"length_m": 2.4, "width_m": 1.8, "margin_m": 0.3},
        "waypoints": snake_waypoints(SWEEP.room),
        "stations": {},
    }
    runner = MissionRunner(loop, driver, build or default, lambda: plan, reset=lambda: None, simulated=True)
    return world, loop, driver, runner


def started(runner, loop):
    runner.start()
    deadline = time.monotonic() + 5
    while runner.status == "loading" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner.status == "running" and loop.autopilot is not None


def ticks(loop, count):
    for _ in range(count):
        loop.tick(time.monotonic())


def test_the_loop_runs_the_mission_to_the_end():
    world, loop, _, runner = make()
    assert runner.snapshot()["status"] == "idle" and runner.snapshot()["mission"] is None
    started(runner, loop)
    for _ in range(40000):
        loop.tick(time.monotonic())
        if runner.status != "running":
            break
    shot = runner.snapshot()
    assert shot["status"] == "done" and shot["mission"]["stats"]["delivered"] == 4
    assert world.objects == [] and loop.autopilot is None
    assert loop.commanded.is_zero()
    json.dumps(shot)  # what the page receives


def test_the_page_sees_what_the_mission_sees_and_commands():
    _, loop, _, runner = make()
    started(runner, loop)
    ticks(loop, 60)
    assert not loop.commanded.is_zero()  # the mission is driving, and the page knows it
    assert loop.snapshot()["cmd"]["x"] != 0 or loop.snapshot()["cmd"]["theta_deg"] != 0


def test_emergency_stop_ends_the_mission_at_once():
    world, loop, driver, runner = make()
    started(runner, loop)
    ticks(loop, 90)
    driver.emergency_stop()
    ticks(loop, 2)
    assert runner.status == "stopped" and runner.message == "emergency stop"
    assert loop.autopilot is None and loop.commanded.is_zero()
    before = (world.x, world.y, world.yaw)
    ticks(loop, 30)
    assert (world.x, world.y, world.yaw) == before  # the wheels really are stopped
    with pytest.raises(ValueError, match="Emergency stop"):
        runner.start()


def test_stop_then_start_again():
    _, loop, _, runner = make()
    started(runner, loop)
    ticks(loop, 30)
    with pytest.raises(ValueError, match="already running"):
        runner.start()
    with pytest.raises(ValueError, match="Stop the mission first"):
        runner.reset()
    runner.stop()
    ticks(loop, 2)
    assert runner.status == "stopped" and runner.message == "stopped from the page" and loop.autopilot is None
    started(runner, loop)
    assert runner.runs == 2


def test_a_mission_that_cannot_be_prepared_says_why():
    def broken(tap):
        raise FileNotFoundError("no model at outputs/train/act_can_v1")

    _, loop, _, runner = make(broken)
    runner.start()
    deadline = time.monotonic() + 5
    while runner.status == "loading" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert runner.status == "failed" and "no model at outputs/train/act_can_v1" in runner.message
    assert loop.autopilot is None


def test_a_mission_that_crashes_stops_the_robot():
    world, loop, _, runner = make()
    started(runner, loop)
    ticks(loop, 30)
    runner.mission.perception.perceive = lambda obs: 1 / 0
    ticks(loop, 2)
    assert runner.status == "failed" and "ZeroDivisionError" in runner.message
    assert loop.autopilot is None and world is not None
    assert loop.robot._vel == BaseVelocity()


@pytest.fixture
def console():
    _, loop, driver, runner = make()
    srv = DriveServer(("127.0.0.1", 0), loop, driver, {"link": "test"}, runner=runner)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    loop.start()
    yield srv
    runner.stop()
    loop.stop()
    srv.shutdown()
    srv.server_close()


def call(srv, path, body=None):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as res:
        payload = res.read()
        kind = res.headers["Content-Type"]
        return json.loads(payload) if kind == "application/json" else (kind, payload)


def test_the_console_is_the_front_page_and_the_driving_page_moves(console):
    assert b"<title>MAKAI console</title>" in call(console, "/")[1]
    assert b"<title>MAKAI control</title>" in call(console, "/drive")[1]
    assert b"<title>MAKAI console</title>" in call(console, "/console")[1]


def test_the_routes_start_and_stop_a_mission(console):
    idle = call(console, "/api/mission")
    assert idle["status"] == "idle" and idle["simulated"] and len(idle["plan"]["waypoints"]) == 8
    assert call(console, "/api/mission/start", {"client": "t"})["status"] in ("loading", "running")
    deadline = time.monotonic() + 5
    while call(console, "/api/mission")["mission"] is None and time.monotonic() < deadline:
        time.sleep(0.05)
    time.sleep(0.5)
    running = call(console, "/api/mission")
    assert running["status"] == "running" and running["mission"]["time_s"] > 0
    with pytest.raises(urllib.error.HTTPError) as refused:
        call(console, "/api/mission/start", {"client": "t"})
    assert refused.value.code == 409 and "already running" in json.loads(refused.value.read())["error"]
    call(console, "/api/mission/stop", {"client": "t"})
    time.sleep(0.3)
    assert call(console, "/api/mission")["status"] == "stopped"
    with pytest.raises(urllib.error.HTTPError) as unknown:
        call(console, "/api/mission/fly", {"client": "t"})
    assert unknown.value.code == 404


def test_the_figures_of_the_docs_are_served(console):
    listing = call(console, "/api/figures")
    assert "training_curves.png" in listing["images"]
    assert any(run["run"] == "act_sock_v1" and run["steps"] > 0 for run in listing["runs"])
    kind, body = call(console, "/figures/training_curves.png")
    assert kind == "image/png" and body[:4] == b"\x89PNG"
    for bad in ("/figures/../../configs/makai.yaml", "/figures/secret.txt", "/figures/nothing.png"):
        with pytest.raises(urllib.error.HTTPError) as refused:
            call(console, bad)
        assert refused.value.code == 404


def test_without_a_runner_the_driving_page_stays_in_front():
    world = sweep_world()
    driver = ManualDriver(LIMITS)
    srv = DriveServer(
        ("127.0.0.1", 0), DriveLoop(SimRobot(world), driver, GEOMETRY), driver, {"link": "wired"}
    )
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        assert b"<title>MAKAI control</title>" in call(srv, "/")[1]
        with pytest.raises(urllib.error.HTTPError) as missing:
            call(srv, "/api/mission")
        assert missing.value.code == 404
    finally:
        srv.shutdown()
        srv.server_close()
