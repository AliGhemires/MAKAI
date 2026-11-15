"""The zone to sweep, traced by driving the robot around it."""

import pytest

from makai.navigation import zone
from makai.navigation.coverage import Room
from makai.navigation.zone import forget_zone, load_zone, save_zone, zone_from_trail


def test_the_zone_is_the_rectangle_around_the_path_driven():
    # From the start pose: to the right, into the room, across to the left, and back.
    path = [(0.0, 0.0), (0.02, -0.42), (1.83, -0.4), (1.8, 0.92), (0.01, 0.9), (-0.05, 0.0)]
    room = zone_from_trail(path)
    assert room == {"length_m": 1.83, "width_m": 1.34, "margin_m": 0.0, "y_offset_m": 0.25}
    assert Room(**room).y_range == pytest.approx((-0.42, 0.92))  # no margin: there are no walls


def test_visiting_the_four_corners_is_enough():
    assert zone_from_trail([(0, 0), (0, -0.5), (2, -0.5), (2, 0.5), (0, 0.5)]) == {
        "length_m": 2.0, "width_m": 1.0, "margin_m": 0.0, "y_offset_m": 0.0,
    }  # fmt: skip


def test_a_path_too_short_is_not_a_zone():
    with pytest.raises(ValueError, match="deep"):
        zone_from_trail([(0, 0), (0.2, 0.6), (0.2, -0.6)])
    with pytest.raises(ValueError, match="wide"):
        zone_from_trail([(0, 0), (1.5, 0.05)])
    assert zone_from_trail([(0, 0), (0.2, 0.1)], check=False)["length_m"] == 0.2  # drawn while it grows


def test_the_traced_zone_is_kept_and_replaces_the_room_of_the_config(tmp_path, monkeypatch):
    from makai.app import sweep_config

    monkeypatch.setattr(zone, "CONFIG_DIR", tmp_path)
    cfg = {"navigation": {"sweep": {"room": {"length_m": 2.0, "width_m": 1.6, "margin_m": 0.3}}}}
    assert load_zone() is None and sweep_config(cfg).room == Room(2.0, 1.6, 0.3)
    traced = zone_from_trail([(0, 0), (0, -0.4), (1.5, -0.4), (1.5, 0.8), (0, 0.8)])
    file = save_zone(traced)
    assert file == tmp_path / "zone.yaml" and file.read_text().startswith("#")
    assert load_zone() == traced
    assert sweep_config(cfg).room == Room(length_m=1.5, width_m=1.2, margin_m=0.0, y_offset_m=0.2)
    forget_zone()
    forget_zone()  # nothing to forget: no error
    assert load_zone() is None and sweep_config(cfg).room == Room(2.0, 1.6, 0.3)
