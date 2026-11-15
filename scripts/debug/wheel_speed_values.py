"""What do this robot's wheel speed readings look like? Recover the raw speeds (steps/s) from
the base velocities stored in a recorded dataset and list the values they take.
Evidence for docs/DEBUG_ODOMETRY.md, section 10.1.

    uv run python scripts/debug/wheel_speed_values.py ~/.cache/huggingface/lerobot/local/makai_pick_sock_v1
"""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1])
info = json.loads((root / "meta" / "info.json").read_text())
names = info["features"]["observation.state"]["names"]
print("state names:", names)
frames = pd.concat(
    [
        pd.read_parquet(p, columns=["observation.state", "action"])
        for p in sorted(root.glob("data/**/*.parquet"))
    ]
)
state = np.stack(frames["observation.state"].to_numpy()).astype(np.float64)
ix, iy, it = (names.index(k) for k in ("x.vel", "y.vel", "theta.vel"))
body = np.stack([state[:, ix], state[:, iy], np.radians(state[:, it])], axis=1)
angles = np.radians(np.array([240, 0, 120]) - 90)
m = np.array([[np.cos(a), np.sin(a), 0.125] for a in angles])
wheel_steps = (body @ m.T) / 0.05 * (180 / np.pi) * (4096 / 360)  # left, back, right, in steps/s
print(
    "frames:",
    len(state),
    " frames with a non-zero wheel speed:",
    int((np.abs(wheel_steps) > 0.5).any(axis=1).sum()),
)
for i, name in enumerate(("left", "back", "right")):
    values = np.round(wheel_steps[:, i]).astype(int)
    off = np.abs(wheel_steps[:, i] - values).max()
    counts = Counter(values.tolist())
    nonzero = sorted((v, c) for v, c in counts.items() if v != 0)
    print(
        f"{name:5s} wheel: distinct values {len(counts)}, farthest from an integer {off:.3f}; non-zero values (value: count):"
    )
    print("      ", ", ".join(f"{v}: {c}" for v, c in nonzero[:60]))
