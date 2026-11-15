"""The recorder's rules: when an episode starts, is saved or is dropped, and what the keys do."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("lerobot")  # the CI installs the core only

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "record.py"
spec = importlib.util.spec_from_file_location("makai_record_script", SCRIPT)
record = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record)


def decide(state: str, manual: bool = False, **now) -> str:
    quiet = dict(right=False, left=False, moved=False, back_home=False, elapsed=0.0)
    return record.decide(state, manual=manual, min_episode=3.0, max_episode=30.0, **{**quiet, **now})


def test_nothing_starts_without_the_right_arrow():
    assert decide("idle") == ""
    assert decide("idle", moved=True) == ""  # the leader's rest is a few degrees off: no episode
    assert decide("idle", back_home=True) == ""
    assert decide("idle", right=True) == "arm"


def test_an_armed_episode_starts_when_the_leader_moves():
    assert decide("armed") == ""
    assert decide("armed", moved=True) == "start"
    assert decide("armed", right=True) == "start"  # start now
    assert decide("armed", left=True) == "cancel"


def test_an_episode_is_saved_back_home_or_by_the_key():
    assert decide("recording", elapsed=5.0) == ""
    assert decide("recording", elapsed=5.0, back_home=True) == "save"
    assert decide("recording", elapsed=1.0, back_home=True) == "False start"
    assert decide("recording", elapsed=31.0) == "Too long"
    assert decide("recording", elapsed=4.0, right=True) == "save"
    assert decide("recording", elapsed=0.3, right=True) == "Too short"  # a double press
    assert decide("recording", elapsed=4.0, left=True) == "Dropped"
    assert decide("recording", elapsed=4.0, left=True, right=True) == "Dropped"


def test_manual_mode_only_obeys_the_keys():
    assert decide("idle", manual=True, right=True) == "start"  # recording starts at the key
    assert decide("recording", manual=True, elapsed=5.0, back_home=True) == ""
    assert decide("recording", manual=True, elapsed=5.0, right=True) == "save"
    assert decide("recording", manual=True, elapsed=31.0) == "Too long"
    assert decide("recording", manual=True, elapsed=5.0, left=True) == "Dropped"


def test_the_status_tells_the_pilot_where_the_arm_is():
    assert record.status("idle", manual=False)[0] == "PRESS RIGHT ARROW"
    lost = record.status("idle", manual=False, at_home=False, far="wrist_roll is 14 degrees away")
    assert lost == (
        "PUT THE LEADER ON ITS REST",
        "wrist_roll is 14 degrees away from home   [RIGHT ARROW = start anyway]",
    )
    assert record.status("armed", manual=False) == (
        "GO",
        "recording starts when you move the leader   [LEFT ARROW = cancel]",
    )
    recording = dict(manual=False, elapsed=6.0, limit=30.0, need=1.0, far="elbow_flex is 31 degrees away")
    assert "pick the object up" in record.status("recording", **recording, left_home=False)[1]
    away = record.status("recording", **recording, left_home=True, at_home=False)[1]
    assert "arm NOT at home: elbow_flex is 31 degrees away" in away
    back = record.status("recording", **recording, left_home=True, at_home=True, still=0.4)
    assert back[0] == "RECORDING 6 s"
    assert "AT HOME: hold still 0.4 / 1.0 s" in back[1]


def test_a_key_acts_once():
    # LeRobot raises exit_early with every key. Left raised after a LEFT ARROW, it used to save
    # the next episode on its first frame.
    events = {"exit_early": True, "rerecord_episode": True, "stop_recording": False}
    assert record.read_keys(events) == (False, True)  # LEFT ARROW
    assert record.read_keys(events) == (False, False)
    events["exit_early"] = True
    assert record.read_keys(events) == (True, False)  # RIGHT ARROW
    assert record.read_keys(events) == (False, False)


def test_escape_is_not_a_right_arrow():
    events = {"exit_early": True, "rerecord_episode": False, "stop_recording": True}
    assert record.read_keys(events) == (False, False)
    assert events["stop_recording"]


def test_one_home_pose_per_dataset(tmp_path, capsys):
    said = []

    def say(text, hint="", speak=True):
        said.append(text)

    first = dict.fromkeys(record.ARM, 20.0)
    record.check_home(first, 1.4, tmp_path, 6.0, say)
    kept = tmp_path / record.HOME_FILE
    assert kept.exists()
    shown = capsys.readouterr().out
    assert "home: {" in shown and "arm_gripper.pos: 1.4" in shown  # the line for configs/arm_poses.yaml
    assert "Careful" not in shown  # a leader that rests closed: going home keeps hold of the object

    record.check_home({**first, record.ARM[0]: 23.0}, 1.4, tmp_path, 6.0, say)  # within the tolerance
    assert said == []
    record.check_home({**first, record.ARM[0]: 40.0}, 1.4, tmp_path, 6.0, say)  # the rest has moved
    assert said == ["Home pose differs"]
    assert f"{record.ARM[0]}: 20.0" in kept.read_text()  # the first session's pose stays the reference

    record.check_home(first, 40.0, tmp_path, 6.0, say)  # a leader that rests open
    assert "Careful: the gripper is open on the rest" in capsys.readouterr().out


def test_the_recorder_confirms_the_mission_home(tmp_path, capsys):
    from makai.config import CONFIG_DIR, load_config
    from makai.manipulation.skills import load_poses

    home = load_poses(CONFIG_DIR / load_config()["manipulation"]["poses_file"])["home"]
    measured = {key: home[key] + 2.0 for key in record.ARM}  # the leader is back on the same rest
    record.check_home(measured, 1.4, tmp_path, 10.0, lambda *a, **k: None)
    assert "Same home pose as the mission's" in capsys.readouterr().out
