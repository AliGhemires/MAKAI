"""Stress-test the object detector and classifier under changes of lighting.

    uv run python scripts/eval_lighting.py data/test_images/*.jpg

Each photo is re-lit artificially (darker, brighter, warmer, cooler, washed out, noisy, with
hard shadows: see `makai.perception.lighting`) and
the detector must still find the same object, with the same category, and report nothing new.
The reference is what the detector finds on the untouched photo, so check those by eye first
(`scripts/detect.py`).

This is a necessary test, not a sufficient one: artificial re-lighting is uniform over the
image, real lighting is not (mixed lamps, hard shadows, reflections). Photos taken under the
real evening lighting remain the test that counts.
"""

from __future__ import annotations

import argparse
import sys

import cv2

from makai.config import load_config
from makai.perception.lighting import LIGHTINGS
from makai.perception.pipeline import build_detector


def iou(a: tuple, b: tuple) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def area(box: tuple) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("images", nargs="+")
    parser.add_argument("--ignore-top", type=float, default=0.22, help="phone photos show clutter at the top")
    parser.add_argument(
        "--width", type=int, default=640, help="resize so the longer side is this (robot camera)"
    )
    args = parser.parse_args()

    p = load_config()["perception"]
    p["floor"]["ignore_top_fraction"] = args.ignore_top
    detector = build_detector(p)

    totals = {name: [0, 0, 0, 0] for name in LIGHTINGS}  # found, right category, extra detections, photos
    for path in args.images:
        bgr = cv2.imread(path)
        if bgr is None:
            continue
        scale = args.width / max(bgr.shape[:2])
        size = (round(bgr.shape[1] * scale), round(bgr.shape[0] * scale))
        image = cv2.cvtColor(cv2.resize(bgr, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        reference = detector.detect(image)
        if not reference:
            print(f"{path}: nothing found on the untouched photo, skipped", file=sys.stderr)
            continue
        main_object = max(reference, key=lambda d: area(d.bbox_xyxy))
        for name, relight in LIGHTINGS.items():
            detections = detector.detect(relight(image))
            match = max(detections, key=lambda d: iou(d.bbox_xyxy, main_object.bbox_xyxy), default=None)
            found = match is not None and iou(match.bbox_xyxy, main_object.bbox_xyxy) >= 0.5
            extra = sum(all(iou(d.bbox_xyxy, r.bbox_xyxy) < 0.3 for r in reference) for d in detections)
            totals[name][0] += found
            totals[name][1] += found and match.category is main_object.category
            totals[name][2] += extra
            totals[name][3] += 1

    n = max(t[3] for t in totals.values())
    print(f"{n} photos, detector={p['detector']}, classifier={p['classifier']}\n")
    print(f"{'lighting':32s} {'found':>7s} {'category':>9s} {'false alarms':>13s}")
    for name, (found, right, extra, count) in totals.items():
        print(f"{name:32s} {found:>4d}/{count:<2d} {right:>6d}/{count:<2d} {extra:>13d}")
    found, right, extra, count = (sum(t[i] for t in totals.values()) for i in range(4))
    print(f"\n{'ALL':32s} {found:>4d}/{count:<3d} {right:>5d}/{count:<3d} {extra:>12d}")
    print(f"found {100 * found / count:.0f} %, right category {100 * right / count:.0f} %")


if __name__ == "__main__":
    main()
