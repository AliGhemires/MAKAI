"""Count how often a detector is right on folders of images that each show ONE known object.

    uv run python scripts/eval_frames.py --clothing data/test_frames/IMG_1378 --trash data/test_frames/IMG_1377
    uv run python scripts/eval_frames.py ... --detector floor --ignore-top 0.22     # compare another detector

Get frames out of a phone video with:
    ffmpeg -i video.MOV -vf "fps=3,scale=-2:640" data/test_frames/<name>/f_%03d.jpg

"ok" means exactly one detection, of the right category, and nothing else. Use frames the
detector was NOT trained on, or the numbers mean nothing.
"""

from __future__ import annotations

import argparse
import collections
from pathlib import Path

import cv2

from makai.config import load_config
from makai.contracts import Category
from makai.perception.pipeline import build_detector

IMAGES = (".jpg", ".jpeg", ".png")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--clothing", nargs="*", default=[], help="folders of images showing one piece of clothing"
    )
    parser.add_argument("--trash", nargs="*", default=[], help="folders of images showing one piece of trash")
    parser.add_argument("--empty", nargs="*", default=[], help="folders of images of the empty floor")
    parser.add_argument(
        "--detector", choices=["learned", "floor", "open_vocab"], help="override perception.detector"
    )
    parser.add_argument(
        "--ignore-top", type=float, help="floor detector: ignore this top fraction of the image"
    )
    args = parser.parse_args()

    p = load_config()["perception"]
    p["detector"] = args.detector or p["detector"]
    if args.ignore_top is not None:
        p["floor"]["ignore_top_fraction"] = args.ignore_top
    detector = build_detector(p)
    print(f"detector: {p['detector']}")

    total = collections.Counter()
    folders = [(f, Category.CLOTHING) for f in args.clothing] + [(f, Category.TRASH) for f in args.trash]
    folders += [(f, None) for f in args.empty]
    for folder, truth in folders:
        counts = collections.Counter()
        for path in sorted(Path(folder).iterdir()):
            if path.suffix.lower() not in IMAGES:
                continue
            detections = detector.detect(cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB))
            right = sum(d.category is truth for d in detections)
            wrong = len(detections) - right
            if truth is None:
                outcome = "ok" if not detections else "false alarm"
            elif (right, wrong) == (1, 0):
                outcome = "ok"
            elif not detections:
                outcome = "nothing found"
            else:
                outcome = "right + something else" if right else "wrong category only"
            counts[outcome] += 1
        total.update(counts)
        n = sum(counts.values())
        label = truth.value if truth else "empty floor"
        print(f"{folder} ({label}, {n} images): " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    n = sum(total.values())
    if n:
        print(f"TOTAL: ok {total['ok']}/{n} ({100 * total['ok'] / n:.0f} %)")


if __name__ == "__main__":
    main()
