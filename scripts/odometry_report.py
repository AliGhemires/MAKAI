"""Read a base trace (data/odometry_trace_*.csv, written by the console through the host) and
say, for every move, what three sources tell: the commands, the servos' speed readings, the
wheel encoders. No tape needed.

    uv run python scripts/odometry_report.py                 # the latest trace
    uv run python scripts/odometry_report.py data/odometry_trace_20261115_181500.csv

How to read it:
- "speeds" and "encoders" should agree within about 1 %. If they do not, the speed readings
  were the problem, and the encoders (now used by the odometry) fix it.
- "wheels" are the encoder steps of each wheel during the move. In a turn on the spot the three
  must be equal; driving straight ahead, left = -right and back = 0. A wheel that lags behind
  did not follow its command: weak servo, low battery, or a wheel that is blocked.
- None of this sees a wheel slipping on the floor: for that, scripts/turn_check.py compares
  the odometry with a marker seen by the camera.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from pathlib import Path

from makai.config import REPO_ROOT, load_config
from makai.robot.lekiwi import STEPS_PER_TURN, BaseGeometry

SETTLE_S = 0.6  # a move ends this long after its last non-zero command


def wrap_steps(delta: float) -> float:
    return (delta + STEPS_PER_TURN / 2) % STEPS_PER_TURN - STEPS_PER_TURN / 2


def load(path: Path) -> list[dict[str, float | None]]:
    with path.open(newline="") as file:
        return [
            {key: (float(value) if value not in ("", None) else None) for key, value in row.items()}
            for row in csv.DictReader(file)
        ]


def split_moves(rows: list[dict]) -> list[list[dict]]:
    """Runs of rows from the first non-zero command to SETTLE_S after the last one."""
    moves, current, last_command = [], [], -math.inf
    for row in rows:
        commanded = any(abs(row[key] or 0.0) > 0 for key in ("cmd_x", "cmd_y", "cmd_theta_deg"))
        if commanded:
            last_command = row["t"]
        if commanded or row["t"] - last_command <= SETTLE_S:
            current.append(row)
        elif current:
            moves.append(current)
            current = []
    if current:
        moves.append(current)
    return [move for move in moves if len(move) >= 5]


def describe(move: list[dict], geometry: BaseGeometry) -> dict:
    """Totals of one move, in the base frame: fine for a turn on the spot or a straight line."""
    names = ("enc_left", "enc_back", "enc_right")
    cmd, speed, wheels = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    has_encoders = all(move[0][name] is not None for name in names)
    for before, row in zip(move, move[1:], strict=False):
        dt = row["t"] - before["t"]
        for i, key in enumerate(("cmd_x", "cmd_y", "cmd_theta_deg")):
            cmd[i] += (before[key] or 0.0) * dt
        for i, key in enumerate(("speed_x", "speed_y", "speed_theta_deg")):
            speed[i] += (row[key] or 0.0) * dt  # as the odometry did: the new reading over the past interval
        if has_encoders:
            for i, name in enumerate(names):
                wheels[i] += wrap_steps(row[name] - before[name])
    encoders = None
    if has_encoders:
        x, y, yaw = geometry.wheel_steps_to_body(dict(zip(geometry.names, wheels, strict=True)))
        encoders = [x, y, math.degrees(yaw)]
    turn = abs(cmd[2]) > 5.0 and math.hypot(cmd[0], cmd[1]) < 0.03
    return {
        "start": move[0]["t"],
        "duration": move[-1]["t"] - move[0]["t"],
        "kind": "turn" if turn else "drive",
        "cmd": cmd,
        "speed": speed,
        "encoders": encoders,
        "wheels": wheels if has_encoders else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("trace", nargs="?", type=Path, help="default: the latest data/odometry_trace_*.csv")
    args = parser.parse_args()
    path = args.trace or max((REPO_ROOT / "data").glob("odometry_trace_*.csv"), default=None)
    if path is None or not path.exists():
        parser.exit(1, "No trace found in data/. Drive the robot from the console first (--link host).\n")
    rows = load(path)
    geometry = BaseGeometry.from_config(load_config()["robot"]["base"])
    print(f"{path}: {len(rows)} observations")

    host = [row["host_t"] for row in rows if row["host_t"] is not None]
    if len(host) > 2:
        periods = [b - a for a, b in zip(host, host[1:], strict=False) if 0 < b - a < 1.0]
        arrivals = [
            b["t"] - a["t"] for a, b in zip(rows, rows[1:], strict=False) if 0 < b["t"] - a["t"] < 1.0
        ]
        print(
            f"stream: the Pi sends every {1000 * statistics.median(periods):.0f} ms "
            f"(longest {1000 * max(periods):.0f} ms); the laptop reads a new one every "
            f"{1000 * statistics.median(arrivals):.0f} ms (longest {1000 * max(arrivals):.0f} ms)"
        )
    else:
        print(
            "stream: this host does not send its clock or the wheel encoders. Update ~/makai_host.py on the Pi."
        )

    moves = [describe(move, geometry) for move in split_moves(rows)]
    if not moves:
        print("No move in this trace.")
        return
    print()
    print(
        f"{'#':>3} {'kind':5} {'s':>5}  {'commanded':>10} {'speeds':>10} {'encoders':>10}  speeds/enc  wheels (steps: left, back, right)"
    )
    ratios = []
    for i, m in enumerate(moves, 1):
        axis = 2 if m["kind"] == "turn" else max((0, 1), key=lambda k: abs(m["cmd"][k]))
        unit, scale = ("deg", 1.0) if axis == 2 else ("cm", 100.0)
        cells = [f"{scale * m['cmd'][axis]:+8.1f} {unit}", f"{scale * m['speed'][axis]:+8.1f} {unit}"]
        ratio, wheels = "", ""
        if m["encoders"] is not None:
            cells.append(f"{scale * m['encoders'][axis]:+8.1f} {unit}")
            if abs(m["encoders"][axis]) > (5.0 if axis == 2 else 0.05):
                value = m["speed"][axis] / m["encoders"][axis]
                ratio = f"{value:8.3f}"
                ratios.append((m["kind"], value))
            wheels = ", ".join(f"{w:+.0f}" for w in m["wheels"])
            if m["kind"] == "turn":
                sizes = [abs(w) for w in m["wheels"]]
                spread = (max(sizes) - min(sizes)) / max(1.0, statistics.fmean(sizes))
                wheels += f"   uneven by {100 * spread:.1f} %"
        else:
            cells.append(f"{'-':>10}")
        print(
            f"{i:3d} {m['kind']:5} {m['duration']:5.1f}  {cells[0]:>10} {cells[1]:>10} {cells[2]:>10}  {ratio:>10}  {wheels}"
        )
    for kind in ("turn", "drive"):
        values = [value for k, value in ratios if k == kind]
        if len(values) >= 2:
            print(
                f"\n{kind}s: speed readings / encoders = {statistics.fmean(values):.3f} on average, "
                f"from {min(values):.3f} to {max(values):.3f} over {len(values)} moves"
            )


if __name__ == "__main__":
    main()
