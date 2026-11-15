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
    quiet = dict(right=False, left=False, settled=False, moved=False, back_home=False, elapsed=0.0)
    return record.decide(state, manual=manual, min_episode=3.0, max_episode=15.0, **{**quiet, **now})


def test_automatic_mode_starts_on_motion_and_saves_back_home():
    assert decide("reset") == ""  # not on its rest yet
    assert decide("reset", settled=True) == "ready"
    assert decide("armed") == ""
    assert decide("armed", moved=True) == "start"
    assert decide("recording", elapsed=5.0) == ""
    assert decide("recording", elapsed=5.0, back_home=True) == "save"
    assert decide("recording", elapsed=1.0, back_home=True) == "False start"
    assert decide("recording", elapsed=16.0) == "Too long"


def test_manual_mode_only_obeys_the_keys():
    assert decide("reset", manual=True) == "ready"  # no need to be on the rest
    assert decide("armed", manual=True, moved=True) == ""
    assert decide("armed", manual=True, right=True) == "start"
    assert decide("recording", manual=True, elapsed=5.0, back_home=True) == ""
    assert decide("recording", manual=True, elapsed=5.0, right=True) == "save"
    assert decide("recording", manual=True, elapsed=16.0) == "Too long"


@pytest.mark.parametrize("manual", [False, True])
def test_the_keys_work_in_both_modes(manual):
    assert decide("reset", manual, right=True) == "start"  # start anyway, even if not settled
    assert decide("armed", manual, right=True) == "start"
    assert decide("recording", manual, elapsed=4.0, right=True) == "save"
    assert decide("recording", manual, elapsed=0.3, right=True) == "Too short"  # a double press
    assert decide("recording", manual, elapsed=4.0, left=True) == "Dropped"
    assert decide("recording", manual, elapsed=4.0, left=True, right=True) == "Dropped"


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
    record.check_home(first, tmp_path, 6.0, say)
    kept = tmp_path / record.HOME_FILE
    assert kept.exists()
    assert "home: {" in capsys.readouterr().out  # the line for configs/arm_poses.yaml, still a placeholder

    record.check_home({**first, record.ARM[0]: 23.0}, tmp_path, 6.0, say)  # within the tolerance
    assert said == []
    record.check_home({**first, record.ARM[0]: 40.0}, tmp_path, 6.0, say)  # the rest has moved
    assert said == ["Home pose differs"]
    assert f"{record.ARM[0]}: 20.0" in kept.read_text()  # the first session's pose stays the reference
