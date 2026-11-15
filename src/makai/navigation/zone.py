"""The zone to sweep, traced by driving the robot around it.

There are no walls: the zone is an imaginary rectangle on the floor. Instead of measuring it
with a tape, the pilot puts the robot at the start pose (in front of the bin, back to it,
facing the room), starts a trace, drives the robot around the edge of the zone, or just to
its corners, and ends the trace. The zone is the rectangle that holds every point the robot
went through, in the frame of the start pose. It always begins at the start line (x = 0).

The other way needs no driving at all (`zone_from_markers`): the bin stands across the zone,
its marker facing the robot. From the start pose the camera reads where the marker is, which
gives the depth of the zone and where the bin and its dock are.

The zone is kept in `configs/zone.yaml` (per room, not in git). While that file exists it
replaces `navigation.sweep.room` of the config, and the stations it holds replace the config's.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import yaml

from makai.config import CONFIG_DIR
from makai.contracts import StationSighting

ZONE_FILE = "zone.yaml"
MIN_LENGTH_M = 0.5  # a smaller trace is a mistake (the robot barely moved), not a zone
MIN_WIDTH_M = 0.3
MIN_AHEAD_M = 0.9  # a marker closer than this is not a bin standing across a zone


def zone_from_trail(points: Iterable[tuple[float, float]], check: bool = True) -> dict[str, float]:
    """The room (`navigation.coverage.Room` fields) that holds a path driven from the start pose.

    The robot's centre went along the edge, so it may go there again: no margin.
    ValueError, with the reason, when the path is too short to be a zone (unless `check` is off).
    """
    points = list(points) or [(0.0, 0.0)]
    length = max(0.0, max(x for x, _ in points))  # what lies behind the start line is the bin's side
    y_min, y_max = min(y for _, y in points), max(y for _, y in points)
    if check and length < MIN_LENGTH_M:
        raise ValueError(f"The zone is only {length:.2f} m deep: drive further into the room.")
    if check and y_max - y_min < MIN_WIDTH_M:
        raise ValueError(
            f"The zone is only {y_max - y_min:.2f} m wide: drive along its left and right edges."
        )
    return {
        "length_m": round(length, 2),
        "width_m": round(y_max - y_min, 2),
        "margin_m": 0.0,
        "y_offset_m": round((y_min + y_max) / 2, 2),
    }


def zone_from_markers(
    sightings: Mapping[object, StationSighting], room: Mapping[str, float], standoff_m: float = 0.35
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """The zone and the stations, from the station markers seen from the start pose.

    Each station stands where its marker is seen; its dock is `standoff_m` in front of it,
    towards the start line. The zone runs from the start line to the nearest dock. Its width
    is not something one marker can tell: it stays as it was in `room`.
    Returns the room and the stations (name -> x, y, dock_x, dock_y), in the frame of the start
    pose. ValueError, with the reason, when no marker stands across the zone.
    """
    ahead = {key: s for key, s in sightings.items() if s.x_m >= MIN_AHEAD_M}
    if not ahead:
        raise ValueError(
            "No station marker in view across the zone. Put the robot at the start pose, facing "
            f"the bin, at least {MIN_AHEAD_M + standoff_m:.1f} m from it, its marker facing the robot."
        )
    stations = {
        getattr(key, "value", str(key)): {
            "x": round(s.x_m, 2),
            "y": round(s.y_m, 2),
            "dock_x": round(s.x_m - standoff_m, 2),
            "dock_y": round(s.y_m, 2),
        }
        for key, s in ahead.items()
    }
    return (
        {
            "length_m": min(place["dock_x"] for place in stations.values()),
            "width_m": float(room["width_m"]),
            "margin_m": 0.0,
            "y_offset_m": float(room.get("y_offset_m", 0.0)),
        },
        stations,
    )


def _read(config_dir: Path | None) -> dict:
    file = Path(config_dir or CONFIG_DIR) / ZONE_FILE
    return (yaml.safe_load(file.read_text()) or {}) if file.exists() else {}


def load_zone(config_dir: Path | None = None) -> dict[str, float] | None:
    """The zone traced or read on the markers, or None when there is none."""
    return _read(config_dir).get("room") or None


def load_zone_stations(config_dir: Path | None = None) -> dict[str, dict[str, float]]:
    """The stations placed by reading their markers from the start pose. Empty when none were."""
    return _read(config_dir).get("stations") or {}


def save_zone(
    room: dict[str, float],
    config_dir: Path | None = None,
    stations: Mapping[str, Mapping[str, float]] | None = None,
) -> Path:
    file = Path(config_dir or CONFIG_DIR) / ZONE_FILE
    header = (
        "# The zone to sweep, set from the console (Mission tab): traced by driving the robot around\n"
        "# it, or read on the bin's marker. While this file exists it replaces navigation.sweep.room,\n"
        "# and its stations replace the config's. Delete it to go back to the config.\n"
    )
    content: dict = {"room": dict(room)}
    if stations:
        content["stations"] = {name: dict(place) for name, place in stations.items()}
    file.write_text(header + yaml.safe_dump(content, sort_keys=False))
    return file


def forget_zone(config_dir: Path | None = None) -> None:
    (Path(config_dir or CONFIG_DIR) / ZONE_FILE).unlink(missing_ok=True)
