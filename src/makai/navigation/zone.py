"""The zone to sweep, traced by driving the robot around it.

There are no walls: the zone is an imaginary rectangle on the floor. Instead of measuring it
with a tape, the pilot puts the robot at the start pose (in front of the bin, back to it,
facing the room), starts a trace, drives the robot around the edge of the zone, or just to
its corners, and ends the trace. The zone is the rectangle that holds every point the robot
went through, in the frame of the start pose. It always begins at the start line (x = 0).

The traced zone is kept in `configs/zone.yaml` (per room, not in git). While that file exists
it replaces `navigation.sweep.room` of the config.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

from makai.config import CONFIG_DIR

ZONE_FILE = "zone.yaml"
MIN_LENGTH_M = 0.5  # a smaller trace is a mistake (the robot barely moved), not a zone
MIN_WIDTH_M = 0.3


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


def load_zone(config_dir: Path | None = None) -> dict[str, float] | None:
    """The traced zone, or None when there is none."""
    file = Path(config_dir or CONFIG_DIR) / ZONE_FILE
    if not file.exists():
        return None
    return (yaml.safe_load(file.read_text()) or {}).get("room") or None


def save_zone(room: dict[str, float], config_dir: Path | None = None) -> Path:
    file = Path(config_dir or CONFIG_DIR) / ZONE_FILE
    header = (
        "# The zone to sweep, traced by driving the robot around it (console, Mission tab).\n"
        "# While this file exists it replaces navigation.sweep.room. Delete it to go back to the config.\n"
    )
    file.write_text(header + yaml.safe_dump({"room": dict(room)}, sort_keys=False))
    return file


def forget_zone(config_dir: Path | None = None) -> None:
    (Path(config_dir or CONFIG_DIR) / ZONE_FILE).unlink(missing_ok=True)
