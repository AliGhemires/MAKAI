import json
import math
import threading
import urllib.error
import urllib.request

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Observation
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import STEPS_PER_DEG, BaseGeometry
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver
from makai.robot.moves import MoveSpec, PreciseMove, TrialLog, WheelOdometry, in_start_frame, wrap_steps

COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
LIMITS = DriveLimits.from_config(COMMITTED["teleop"]["drive"])
DT = 0.02


def wheel_steps_for(dx, dy, dyaw):
    """Encoder steps each wheel turns for a small base motion (inverse of the odometry)."""
    out = {}
    for name, angle in zip(GEOMETRY.names, GEOMETRY.angles_rad, strict=True):
        rim = math.cos(angle) * dx + math.sin(angle) * dy + GEOMETRY.base_radius_m * dyaw
        out[name] = math.degrees(rim / GEOMETRY.wheel_radius_m) * STEPS_PER_DEG
    return out


class EncoderRobot:
    """Wheels turn exactly as commanded and report integer encoder positions that wrap at 4096.

    `scale`: how far the robot really goes compared with what its wheels say (slip, or a
    wrong wheel radius in the config). `lag`: servo response time constant in seconds.
    """

    def __init__(self, scale=1.0, lag=0.0, stuck=False):
        self.scale, self.lag, self.stuck = scale, lag, stuck
        self.steps = dict.fromkeys(GEOMETRY.names, 4000.0)  # close to the wrap on purpose
        self.v = (0.0, 0.0, 0.0)  # what the wheels actually do (lagging the command)
        self.true = [0.0, 0.0, 0.0]
        self.sent = []

    def drive(self, cmd):
        self.sent.append(cmd)
        a = 1.0 if self.lag == 0 else 1 - math.exp(-DT / self.lag)
        target = (0.0, 0.0, 0.0) if self.stuck else (cmd.x, cmd.y, cmd.theta)
        self.v = tuple(v + a * (t - v) for v, t in zip(self.v, target, strict=True))
        vx, vy, w = self.v
        for name, steps in wheel_steps_for(vx * DT, vy * DT, w * DT).items():
            self.steps[name] = (self.steps[name] + steps) % 4096
        c, s = math.cos(self.true[2]), math.sin(self.true[2])
        self.true[0] += self.scale * (c * vx - s * vy) * DT
        self.true[1] += self.scale * (s * vx + c * vy) * DT
        self.true[2] += self.scale * w * DT

    def wheel_positions(self):
        return {name: int(round(steps)) % 4096 for name, steps in self.steps.items()}

    def get_observation(self):
        return Observation(stamp=0.0, base_velocity=BaseVelocity(*self.v))

    def stop(self):
        self.v = (0.0, 0.0, 0.0)


def run_move(spec, robot=None, seconds=30.0):
    """Drive a precise move through a DriveLoop at 50 Hz until it ends; returns (loop, robot)."""
    robot = robot or EncoderRobot()
    loop = DriveLoop(robot, ManualDriver(LIMITS), GEOMETRY, truth=lambda: tuple(robot.true))
    t = 0.0
    loop.tick(t)  # first tick: finds the encoders
    loop.start_move("a", spec, t)
    while loop.snapshot()["move"] is not None and t < seconds:
        t += DT
        loop.tick(t)
    return loop, robot


def test_encoder_difference_across_the_wrap():
    assert wrap_steps(10 - 4090) == 16
    assert wrap_steps(4090 - 10) == -16
    assert wrap_steps(0) == 0


def test_wheel_odometry_follows_straight_lines_and_turns_across_the_wrap():
    odo, steps = WheelOdometry(GEOMETRY), dict.fromkeys(GEOMETRY.names, 4090.0)
    odo.update({n: int(s) for n, s in steps.items()})
    for _ in range(100):  # 10 cm forward in 1 mm steps
        for name, d in wheel_steps_for(0.001, 0, 0).items():
            steps[name] = (steps[name] + d) % 4096
        odo.update({n: round(s) % 4096 for n, s in steps.items()})
    assert odo.x == pytest.approx(0.1, abs=5e-4)
    assert abs(odo.y) < 5e-4 and abs(odo.yaw) < math.radians(0.3)
    for _ in range(90):  # then 90 degrees on the spot
        for name, d in wheel_steps_for(0, 0, math.radians(1)).items():
            steps[name] = (steps[name] + d) % 4096
        odo.update({n: round(s) % 4096 for n, s in steps.items()})
    assert math.degrees(odo.yaw) == pytest.approx(90, abs=0.5)
    assert odo.x == pytest.approx(0.1, abs=1e-3)


@pytest.mark.parametrize(
    "spec",
    [
        MoveSpec("x", 0.10, 0.1),
        MoveSpec("x", -0.25, 0.2),
        MoveSpec("y", 0.05, 0.05),
        MoveSpec("y", -0.3, 0.1),
    ],
)
def test_straight_moves_stop_within_a_millimetre(spec):
    loop, robot = run_move(spec)
    trial = loop.last_trial
    assert trial["status"] == "done"
    assert trial["wheels"] == pytest.approx(abs(spec.target) * 100, abs=0.15)  # cm
    assert trial["off_axis_cm"] < 0.1 and abs(trial["heading_drift_deg"]) < 0.3
    speeds = [math.hypot(v.x, v.y) for v in robot.sent]
    assert max(speeds) <= spec.speed + 1e-3  # plus a tiny correction on the other axis


def test_turn_stops_within_half_a_degree_and_stays_on_the_spot():
    loop, _ = run_move(MoveSpec("theta", math.radians(-90), math.radians(45)))
    trial = loop.last_trial
    assert trial["move"] == "turn right" and trial["status"] == "done"
    assert trial["wheels"] == pytest.approx(90, abs=0.5)  # degrees, along the move
    assert trial["off_axis_cm"] < 0.2


def test_speed_ramps_up_and_slows_down_before_the_end():
    spec = MoveSpec("x", 0.5, 0.2)
    _, robot = run_move(spec)
    xs = [v.x for v in robot.sent if v.x > 0]
    assert xs[0] <= 0.3 * DT + 0.02  # gentle start
    assert max(xs) == pytest.approx(0.2)
    assert xs[-1] < 0.03  # creeping at the end


def test_servo_lag_gives_a_small_overshoot_that_is_reported_not_hidden():
    loop, _ = run_move(MoveSpec("x", 0.2, 0.2), EncoderRobot(lag=0.08))
    trial = loop.last_trial
    assert trial["status"] == "done"
    assert 0 <= trial["wheels"] - 20 < 0.5  # overshoot below 5 mm, and it never backs up


def test_sideways_drift_is_corrected_on_the_way():
    class DriftingRobot(EncoderRobot):
        def drive(self, cmd):  # a slipping wheel pushes the base to the left while it moves
            super().drive(BaseVelocity(cmd.x, cmd.y + 0.1 * cmd.x, cmd.theta))

    loop, _ = run_move(MoveSpec("x", 0.5, 0.1), DriftingRobot())
    assert loop.last_trial["off_axis_cm"] < 0.6  # uncorrected it would be about 5 cm


def test_a_stuck_robot_times_out():
    loop, _ = run_move(MoveSpec("x", 0.1, 0.1), EncoderRobot(stuck=True), seconds=60)
    assert loop.last_trial["status"] == "timeout"


def test_cancel_and_emergency_stop_end_the_move():
    robot = EncoderRobot()
    loop = DriveLoop(robot, ManualDriver(LIMITS), GEOMETRY)
    loop.tick(0.0)
    loop.start_move("a", MoveSpec("x", 1.0, 0.1), 0.0)
    for i in range(1, 50):
        loop.tick(i * DT)
    loop.cancel_move()
    loop.tick(1.0)
    assert loop.last_trial["status"] == "cancelled" and 0 < loop.last_trial["wheels"] < 100
    loop.start_move("a", MoveSpec("x", 1.0, 0.1), 1.0)
    loop.tick(1.02)
    loop.driver.emergency_stop()
    loop.tick(1.04)
    assert loop.last_trial["status"] == "stopped"
    assert loop.snapshot()["move"] is None


def test_moves_are_refused_when_unsafe():
    robot = EncoderRobot()
    driver = ManualDriver(LIMITS)
    loop = DriveLoop(robot, driver, GEOMETRY)
    loop.tick(0.0)
    driver.command("other", 1, 0, 0, 1.0, 0.0, label="iPhone")
    loop.tick(DT)
    with pytest.raises(ValueError, match="still moving"):
        loop.start_move("a", MoveSpec("x", 0.1, 0.1), DT)
    for i in range(2, 100):  # the iPhone lets go: the robot brakes
        driver.command("other", 0, 0, 0, 1.0, i * DT)
        loop.tick(i * DT)
    with pytest.raises(ValueError, match="Another device"):
        loop.start_move("a", MoveSpec("x", 0.1, 0.1), 2.0)
    driver.emergency_stop()
    with pytest.raises(ValueError, match="Emergency"):
        loop.start_move("other", MoveSpec("x", 0.1, 0.1), 2.0)


def test_sticks_restart_from_standstill_after_a_move():
    loop, robot = run_move(MoveSpec("x", 0.1, 0.1))
    loop.driver.command("a", 1, 0, 0, 1.0, 100.0)
    loop.tick(100.0)
    loop.tick(100.0 + DT)
    assert robot.sent[-1].x <= LIMITS.accel_m_s2 * DT + 1e-9


def test_odometry_uses_the_encoders_when_the_robot_has_them():
    loop, _ = run_move(MoveSpec("x", 0.1, 0.1))
    snap = loop.snapshot()
    assert snap["odometry_source"] == "wheel encoders"
    assert snap["pose"]["x"] == pytest.approx(0.1, abs=0.002)
    assert loop.reset_odometry() and loop.snapshot()["pose"]["x"] == 0


def test_simulated_tape_shows_a_miscalibrated_robot():
    loop, _ = run_move(MoveSpec("x", 0.2, 0.1), EncoderRobot(scale=0.95))
    trial = loop.last_trial
    assert trial["wheels"] == pytest.approx(20, abs=0.15)
    assert trial["sim_truth"] == pytest.approx(19, abs=0.15)


@pytest.mark.parametrize(
    "bad",
    [
        ("z", 0.1, 0.1),
        ("x", 0.0, 0.1),
        ("x", 5.0, 0.1),
        ("x", float("nan"), 0.1),
        ("theta", 20.0, 1),
        ("y", 0.1, 0),
    ],
)
def test_invalid_moves_are_rejected(bad):
    with pytest.raises(ValueError):
        MoveSpec(*bad)


def test_moves_never_go_faster_than_the_driving_limits():
    move = PreciseMove(MoveSpec("x", 1.0, 5.0), (0, 0, 0), 0.0, max_lin_m_s=0.25)
    assert move.cruise == 0.25


def test_start_frame_is_relative_to_the_starting_heading():
    forward, left, turned = in_start_frame((1.0, 1.0, math.pi / 2), (1.0, 1.5, math.pi / 2))
    assert forward == pytest.approx(0.5) and left == pytest.approx(0) and turned == 0


def fake_result(axis, target, wheels, status="done"):
    return {
        "axis": axis,
        "target": target,
        "speed": 0.1,
        "wheels": wheels,
        "off_axis_m": 0.001,
        "heading_drift_rad": 0.0,
        "duration_s": 2.0,
        "status": status,
    }


def test_trial_log_statistics_and_calibration_suggestions(tmp_path):
    log = TrialLog(tmp_path / "trials.csv")
    for _ in range(3):  # the wheels say 10 cm, the tape 9.6 cm: the wheels are smaller than configured
        trial = log.add(fake_result("x", 0.10, 0.1001), GEOMETRY)
        log.measure(trial["id"], 9.6)
    for _ in range(3):  # the robot turns 87 degrees when its wheels say 90
        trial = log.add(fake_result("theta", math.radians(90), math.radians(90)), GEOMETRY)
        log.measure(trial["id"], 87)
    log.add(fake_result("y", -0.1, -0.05, status="cancelled"), GEOMETRY)
    stats = log.snapshot()["stats"]
    x = stats["x"]
    assert x["moves"] == 3 and x["measured"] == 3
    assert x["tape_error_mean"] == pytest.approx(-0.4)
    assert x["tape_over_wheels"] == pytest.approx(0.959, abs=1e-3)
    assert x["suggestion"]["key"] == "wheel_radius_m"
    assert x["suggestion"]["value"] == pytest.approx(0.05 * 9.6 / 10.01, abs=1e-5)
    turns = stats["theta"]["suggestion"]
    assert turns["key"] == "base_radius_m"
    assert turns["value"] == pytest.approx(0.125 * 90 / 87, abs=1e-5)
    assert "y" not in stats  # a cancelled move is not evidence


def test_trial_log_needs_three_measurements_before_suggesting():
    log = TrialLog()
    for _ in range(2):
        log.measure(log.add(fake_result("x", 0.1, 0.1), GEOMETRY)["id"], 9.9)
    assert "suggestion" not in log.snapshot()["stats"]["x"]


def test_trial_log_survives_a_restart_and_keeps_numbering_after_clear(tmp_path):
    path = tmp_path / "trials.csv"
    log = TrialLog(path)
    first = log.add(fake_result("x", -0.2, -0.199), GEOMETRY)
    log.measure(first["id"], 19.7)
    log.add(fake_result("theta", math.radians(45), math.radians(45.2)), GEOMETRY)
    again = TrialLog(path)
    assert [t["move"] for t in again.trials] == ["back", "turn left"]
    assert again.trials[0]["tape"] == 19.7 and again.trials[0]["wheels"] == pytest.approx(19.9)
    again.clear()
    assert again.trials == [] and len(list(tmp_path.glob("trials_*.csv"))) == 1  # a backup is kept
    assert again.add(fake_result("x", 0.1, 0.1), GEOMETRY)["id"] == 3


def test_trial_log_rejects_bad_measurements():
    log = TrialLog()
    trial = log.add(fake_result("x", 0.1, 0.1), GEOMETRY)
    with pytest.raises(ValueError):
        log.measure(trial["id"], -3)
    with pytest.raises(ValueError):
        log.measure(trial["id"], float("nan"))
    with pytest.raises(KeyError):
        log.measure(99, 10)
    assert log.measure(trial["id"], None)["tape"] is None


@pytest.fixture
def server():
    robot = EncoderRobot()
    loop = DriveLoop(robot, ManualDriver(LIMITS), GEOMETRY)
    loop.tick(0.0)
    srv = DriveServer(("127.0.0.1", 0), loop, loop.driver, {"link": "test"})
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(srv, path, body=None):
    url = f"http://127.0.0.1:{srv.server_address[1]}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as res:
        payload = res.read().decode()
        return json.loads(payload) if res.headers["Content-Type"] == "application/json" else payload


def error_of(srv, path, body):
    with pytest.raises(urllib.error.HTTPError) as err:
        call(srv, path, body)
    return err.value.code, json.loads(err.value.read())["error"]


def test_server_runs_a_move_and_records_the_tape(server):
    state = call(server, "/api/move", {"client": "p", "axis": "x", "target": 0.05, "speed": 0.1})
    assert state["move"]["move"] == "forward" and state["move"]["target"] == 5
    assert error_of(server, "/api/move", {"client": "p", "axis": "x", "target": 0.05, "speed": 0.1}) == (
        409,
        "A move is already running.",
    )
    assert error_of(server, "/api/reset_odometry", {"client": "p"})[0] == 409
    call(server, "/api/move/cancel", {"client": "p"})
    loop = server.loop
    t = 0.0
    while loop.snapshot()["move"] is not None:
        t += DT
        loop.tick(t)
    trials = call(server, "/api/trials")
    assert trials["trials"][0]["status"] == "cancelled"
    call(server, "/api/trials/measure", {"client": "p", "id": 1, "tape": 0.2})
    assert call(server, "/api/trials")["trials"][0]["tape"] == 0.2
    assert "move,unit,target" in call(server, "/api/trials.csv")
    assert error_of(server, "/api/trials/measure", {"client": "p", "id": 42, "tape": 1})[0] == 404
    assert error_of(server, "/api/trials/measure", {"client": "p", "id": 1, "tape": -1})[0] == 400
    call(server, "/api/trials/clear", {"client": "p"})
    assert call(server, "/api/trials")["trials"] == []


def test_server_rejects_invalid_moves(server):
    code, message = error_of(server, "/api/move", {"client": "p", "axis": "x", "target": 50, "speed": 0.1})
    assert code == 400 and "at most" in message
    assert error_of(server, "/api/move", {"axis": "x", "target": 0.1, "speed": 0.1})[0] == 400
