import math
import time
from types import SimpleNamespace

import pytest
import yaml

from makai.config import CONFIG_DIR
from makai.contracts import BaseVelocity, Robot
from makai.robot import lekiwi
from makai.robot.lekiwi import BaseGeometry, LeKiwiRobot, WiredBase

# The committed values, not a laptop's local.yaml.
COMMITTED = yaml.safe_load((CONFIG_DIR / "makai.yaml").read_text())
GEOMETRY = BaseGeometry.from_config(COMMITTED["robot"]["base"])
STOPPED = dict.fromkeys(GEOMETRY.names, 0)


def drive_pi_body_to_raw(x, y, theta_deg):
    """The formula that drove the real robot on 14 November (drive_pi.py), as a reference."""
    out = []
    for angle in (math.radians(a - 90) for a in (240, 0, 120)):
        v = math.cos(angle) * x + math.sin(angle) * y + 0.125 * math.radians(theta_deg)
        out.append(int(max(-3000, min(3000, round(math.degrees(v / 0.05) * 4096 / 360)))))
    return out


WHEELS = ",".join(GEOMETRY.names)
ARM_ANGLES = {"arm_shoulder_pan": -12.0, "arm_shoulder_lift": 35.0, "arm_elbow_flex": -80.0,
              "arm_wrist_flex": 10.0, "arm_wrist_roll": 0.0, "arm_gripper": 40.0}  # fmt: skip


class FakeBus:
    """Stands in for lerobot's SerialMotorsBus: the three wheels, plus the arm if `arm`."""

    def __init__(self, arm=False, arm_answers=True):
        self.calls = []
        ids = {**GEOMETRY.motor_ids, **(lekiwi.ARM_MOTOR_IDS if arm else {})}
        self.motors = {name: SimpleNamespace(id=motor_id) for name, motor_id in ids.items()}
        self.arm_answers = arm_answers
        self.present = dict(STOPPED)
        self.voltage = dict.fromkeys(GEOMETRY.names, 124)

    def connect(self):
        if any(name.startswith("arm_") for name in self.motors) and not self.arm_answers:
            raise RuntimeError("Missing motor IDs: [1, 2, 3, 4, 5, 6]")
        self.calls.append("connect")

    def disconnect(self, disable_torque=True):
        self.calls.append(f"disconnect, torque off: {disable_torque}")

    def disable_torque(self, motors=None):
        self.calls.append(f"torque off {','.join(motors or self.motors)}")

    def enable_torque(self, motors=None):
        self.calls.append(f"torque on {','.join(motors or self.motors)}")

    def set_operating_mode(self, mode, motors=None):
        self.calls.append(f"mode {mode} {','.join(motors or self.motors)}")

    def sync_write(self, register, values, normalize=True):
        self.calls.append((register, dict(values)))

    def sync_read(self, register, motors=None, normalize=True):
        names = list(motors or self.motors)
        values = {
            "Present_Velocity": {**dict.fromkeys(self.motors, 0), **self.present},
            "Present_Voltage": {**dict.fromkeys(self.motors, 123), **self.voltage},
            "Present_Temperature": dict.fromkeys(self.motors, 31),
            "Present_Position": {**dict.fromkeys(GEOMETRY.names, 2048), **ARM_ANGLES},
            "Present_Load": dict.fromkeys(self.motors, -125),  # raw: 0.1 % of max torque
            "Present_Current": dict.fromkeys(self.motors, 20),  # raw: 6.5 mA
            "Torque_Enable": {name: int(name.startswith("base_")) for name in self.motors},
            "Status": {name: 4 * (name == "arm_elbow_flex") for name in self.motors},  # bit 2: overheat
            "Moving": dict.fromkeys(self.motors, 0),
        }[register]
        assert normalize == (register == "Present_Position" and all(n.startswith("arm_") for n in names)), (
            "raw for the wheels, degrees for the arm"
        )
        return {name: values[name] for name in names}

    @property
    def last_goal(self):
        return next(values for register, values in reversed(self.writes()) if register == "Goal_Velocity")

    def writes(self):
        return [call for call in self.calls if isinstance(call, tuple)]


def test_config_holds_the_wheel_setup_measured_on_the_robot():
    base = COMMITTED["robot"]["base"]
    assert COMMITTED["robot"]["link"] == "host"  # the mission keeps going through the host by default
    assert base["port"] == "/dev/ttyACM0"
    assert GEOMETRY.motor_ids == {"base_left_wheel": 7, "base_back_wheel": 8, "base_right_wheel": 9}
    assert (GEOMETRY.wheel_radius_m, GEOMETRY.base_radius_m, GEOMETRY.max_wheel_raw) == (0.05, 0.125, 3000)
    assert [round(math.degrees(a)) for a in GEOMETRY.angles_rad] == [150, -90, 30]


@pytest.mark.parametrize(
    "command",
    [(0.15, 0, 0), (-0.15, 0, 0), (0, 0.15, 0), (0, -0.15, 0), (0, 0, 45), (0, 0, -45), (0.1, 0.05, 20)],
)
def test_wheel_speeds_match_the_formula_tested_on_the_robot(command):
    assert list(GEOMETRY.body_to_wheel_raw(*command).values()) == drive_pi_body_to_raw(*command)


def test_forward_spins_left_and_right_wheels_opposite_ways_and_not_the_back_wheel():
    raw = GEOMETRY.body_to_wheel_raw(0.15, 0, 0)
    assert raw["base_back_wheel"] == 0
    assert raw["base_left_wheel"] == -raw["base_right_wheel"]
    assert raw["base_right_wheel"] > 0


def test_rotation_spins_all_wheels_the_same_way():
    raw = GEOMETRY.body_to_wheel_raw(0, 0, 45)
    assert len(set(raw.values())) == 1
    assert raw["base_back_wheel"] > 0


def test_fast_commands_are_scaled_down_keeping_the_direction():
    slow, fast = GEOMETRY.body_to_wheel_raw(0.1, 0.05, 0), GEOMETRY.body_to_wheel_raw(1.0, 0.5, 0)
    assert max(abs(v) for v in fast.values()) == GEOMETRY.max_wheel_raw
    ratio = GEOMETRY.max_wheel_raw / max(abs(v) for v in slow.values())
    for name in GEOMETRY.names:
        assert fast[name] == pytest.approx(slow[name] * ratio, abs=2)


def test_wheel_speeds_convert_back_to_the_base_velocity():
    body = GEOMETRY.wheel_raw_to_body(GEOMETRY.body_to_wheel_raw(0.12, -0.04, 30))
    assert body["x.vel"] == pytest.approx(0.12, abs=1e-3)
    assert body["y.vel"] == pytest.approx(-0.04, abs=1e-3)
    assert body["theta.vel"] == pytest.approx(30, abs=0.1)


def test_robot_drives_the_wheels_over_the_wire():
    bus = FakeBus()
    robot = LeKiwiRobot(WiredBase(bus, GEOMETRY, watchdog_s=60), camera_names=())
    assert isinstance(robot, Robot)
    robot.connect()
    assert bus.calls[:4] == [
        "connect",
        f"torque off {WHEELS}",
        f"mode velocity {WHEELS}",
        f"torque on {WHEELS}",
    ]
    robot.drive(BaseVelocity(x=0.15))
    assert bus.last_goal == GEOMETRY.body_to_wheel_raw(0.15, 0, 0)
    robot.drive(BaseVelocity(theta=math.radians(45)))
    assert bus.last_goal == GEOMETRY.body_to_wheel_raw(0, 0, 45)
    robot.disconnect()
    assert bus.last_goal == STOPPED
    assert bus.calls[-2:] == [f"torque off {WHEELS}", "disconnect, torque off: False"]


def test_wired_base_stops_the_wheels_when_commands_stop():
    bus = FakeBus()
    base = WiredBase(bus, GEOMETRY, watchdog_s=0.5)
    base.send_action({"x.vel": 0.1, "y.vel": 0.0, "theta.vel": 0.0})
    assert not base.check_watchdog(time.monotonic())  # fresh command: keep going
    assert base.check_watchdog(time.monotonic() + 1.0)  # stale: stop
    assert bus.last_goal == STOPPED
    writes = len(bus.writes())
    assert not base.check_watchdog(time.monotonic() + 2.0)  # already stopped: leave the bus alone
    assert len(bus.writes()) == writes


def test_wired_robot_reports_measured_velocity_and_battery_and_refuses_the_arm():
    bus = FakeBus()
    bus.present = GEOMETRY.body_to_wheel_raw(0.1, 0.0, 0.0)
    robot = LeKiwiRobot(WiredBase(bus, GEOMETRY), camera_names=())
    obs = robot.get_observation()
    assert obs.base_velocity.x == pytest.approx(0.1, abs=1e-3)
    assert obs.images == {} and obs.arm == {}
    assert robot.battery_voltage() == pytest.approx(12.4)
    robot.drive(BaseVelocity(x=0.1))
    with pytest.raises(RuntimeError, match="host"):
        robot.move_arm({"arm_gripper.pos": 50.0})
    assert bus.last_goal == STOPPED  # the base was stopped before refusing


def test_link_from_config_picks_the_wired_base_with_the_configured_port(monkeypatch):
    opened = []
    monkeypatch.setattr(
        lekiwi, "make_wheel_bus", lambda port, geometry, arm=None: opened.append(port) or FakeBus()
    )
    monkeypatch.setattr(lekiwi, "load_arm_calibration", lambda path: None)
    cfg = {"robot": {**COMMITTED["robot"], "link": "wired"}}
    robot = LeKiwiRobot.from_config(cfg)
    assert isinstance(robot.client, WiredBase) and robot.camera_names == ()
    assert opened == ["/dev/ttyACM0"]
    assert robot.client.watchdog_s == 0.5
    with pytest.raises(ValueError, match="robot.link"):
        LeKiwiRobot.from_config(cfg, link="bluetooth")


def test_battery_is_unknown_through_the_host():
    class Client:
        def send_action(self, action): ...

    assert LeKiwiRobot(Client()).battery_voltage() is None


def test_the_arm_is_read_but_never_written_to():
    bus = FakeBus(arm=True)
    robot = LeKiwiRobot(WiredBase(bus, GEOMETRY, watchdog_s=60), camera_names=())
    robot.connect()
    robot.drive(BaseVelocity(x=0.1))
    obs = robot.get_observation()
    assert obs.arm == {f"{name}.pos": value for name, value in ARM_ANGLES.items()}
    details = robot.motor_details()
    assert sorted(details) == sorted(bus.motors)
    assert details["arm_gripper"]["id"] == 6 and details["base_back_wheel"]["id"] == 8
    assert details["base_left_wheel"] == {
        "id": 7,
        "position": 2048,
        "velocity": 0,
        "load_pct": -12.5,
        "current_ma": 130,
        "voltage_v": 12.4,
        "temperature_c": 31,
        "torque": True,
        "moving": False,
        "errors": [],
    }
    assert details["arm_elbow_flex"]["errors"] == ["overheat"] and not details["arm_elbow_flex"]["torque"]
    robot.disconnect()
    for call in bus.calls:  # torque, mode and goals: wheels only, and the arm keeps its torque
        text = str(call)
        assert "arm_" not in text, call
    assert bus.calls[-1] == "disconnect, torque off: False"


def test_without_an_answering_arm_the_wheels_still_drive():
    arm_bus, wheels_bus = FakeBus(arm=True, arm_answers=False), FakeBus()
    base = WiredBase(arm_bus, GEOMETRY, watchdog_s=60, fallback_bus=wheels_bus)
    robot = LeKiwiRobot(base, camera_names=())
    robot.connect()
    assert base.bus is wheels_bus and base.arm == []
    robot.drive(BaseVelocity(x=0.1))
    assert wheels_bus.last_goal == GEOMETRY.body_to_wheel_raw(0.1, 0, 0)
    assert robot.get_observation().arm == {}


def test_wired_config_adds_the_arm_when_it_is_calibrated(monkeypatch):
    built = []
    monkeypatch.setattr(lekiwi, "load_arm_calibration", lambda path: {"arm_gripper": "calibration"})
    monkeypatch.setattr(
        lekiwi, "make_wheel_bus", lambda port, geometry, arm=None: built.append(arm) or FakeBus()
    )
    robot = LeKiwiRobot.from_config({"robot": {**COMMITTED["robot"], "link": "wired"}})
    assert built == [{"arm_gripper": "calibration"}, None]  # with the arm, and a wheels-only fallback
    assert robot.client.fallback_bus is not None


def test_motor_details_are_unknown_through_the_host():
    class Client:
        def send_action(self, action): ...

    assert LeKiwiRobot(Client()).motor_details() is None
