"""The trial script: what it concludes from the gripper readings."""

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("lerobot")  # the CI installs the core only

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "try_pick.py"
spec = importlib.util.spec_from_file_location("makai_try_pick_script", SCRIPT)
try_pick = importlib.util.module_from_spec(spec)
spec.loader.exec_module(try_pick)


def test_a_threshold_between_held_and_empty():
    readings = [(True, 5.7), (True, 4.1), (False, 2.3), (True, 6.0), (False, 2.4)]
    assert "gripper_open_above: 3.2" in try_pick.grasp_check(readings)  # halfway between 2.4 and 4.1


def test_no_threshold_when_they_overlap():
    assert "overlap" in try_pick.grasp_check([(True, 3.0), (False, 3.1), (True, 6.0)])


def test_both_kinds_of_trial_are_needed():
    assert "are needed" in try_pick.grasp_check([(True, 5.0), (True, 6.0)])
    assert "are needed" in try_pick.grasp_check([])
