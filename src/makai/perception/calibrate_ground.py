"""Calibrate the pixel -> floor mapping of the front camera.

    uv run python scripts/make_markers.py          # then print assets/markers/ground_sheet.png at 100 %
    uv run makai-calibrate-ground                  # live, from the robot
    uv run makai-calibrate-ground --image a.png:0.20 --image b.png:0.45   # offline

Place the sheet flat on the floor, centred on the robot axis, at two or three
distances (for example 0.15 m, 0.35 m, 0.60 m). The result is written to
configs/ground_plane.yaml: commit it, it is a property of the robot, not of a laptop.
"""

from __future__ import annotations

import argparse

import cv2
import numpy as np

from makai.config import CONFIG_DIR, load_config
from makai.perception.calibration import sheet_correspondences
from makai.perception.geometry import GroundPlane


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="FILE:DISTANCE_M",
        help="offline image and the sheet's near-edge distance",
    )
    parser.add_argument("--scale", type=float, default=1.0, help="measured marker side in mm / 60")
    args = parser.parse_args()
    cfg = load_config()

    pixels, ground = [], []

    def add(image_rgb: np.ndarray, distance_m: float) -> None:
        px, gr = sheet_correspondences(image_rgb, distance_m, args.scale)
        print(f"  {len(px) // 4} markers found at {distance_m:.2f} m")
        pixels.append(px)
        ground.append(gr)

    if args.image:
        for spec in args.image:
            path, distance = spec.rsplit(":", 1)
            add(cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB), float(distance))
    else:
        from makai.robot.lekiwi import LeKiwiRobot

        robot = LeKiwiRobot.from_config(cfg)
        robot.connect()
        try:
            while text := input(
                "Distance base centre -> near edge of the sheet, in metres (empty to finish): "
            ).strip():
                for _ in range(10):  # flush stale frames
                    obs = robot.get_observation()
                add(obs.images["front"], float(text))
        finally:
            robot.disconnect()

    pixels_all, ground_all = np.concatenate(pixels), np.concatenate(ground)
    if len(pixels_all) < 8:
        raise SystemExit("Not enough markers detected: check lighting, focus, and that the sheet is in view.")
    plane = GroundPlane.fit(pixels_all, ground_all)
    error = plane.reprojection_error_m(pixels_all, ground_all)
    out = CONFIG_DIR / cfg["perception"]["ground_plane_file"]
    plane.save(out)
    print(f"Saved {out} from {len(pixels_all)} points, mean error {error * 1000:.1f} mm (aim for < 5 mm)")


if __name__ == "__main__":
    main()
