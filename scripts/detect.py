"""Try the object detector without the robot: on image files or on a laptop webcam.

    uv run python scripts/detect.py --image photo1.jpg photo2.jpg   # annotated copies in outputs/detect/
    uv run python scripts/detect.py --camera 0                      # live, shown in Rerun

The detector and its settings come from configs/makai.yaml (`perception`). To try something
else without touching the shared config:

    --detector floor --ignore-top 0.22        # "not carpet" detector; phone photos show clutter at the top
    --detector open_vocab --clothing "rolled up sock" clothing --confidence 0.3
    --classifier clip                         # clothing vs the rest, on the cropped object

Run from the repo root so the downloaded weights are found.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from makai.config import REPO_ROOT, load_config
from makai.contracts import Category, Detection
from makai.perception.pipeline import build_detector

COLORS = {Category.CLOTHING: (60, 120, 255), Category.TRASH: (255, 140, 0), Category.UNKNOWN: (160, 160, 160)}


def annotate(image_rgb: np.ndarray, detections: list[Detection]) -> np.ndarray:
    out = image_rgb.copy()
    scale = max(1.0, out.shape[1] / 640)  # keep boxes and text readable on large photos
    thick = int(round(2 * scale))
    for det in detections:
        x1, y1, x2, y2 = (int(v) for v in det.bbox_xyxy)
        color = COLORS[det.category]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thick)
        text = f"{det.label} [{det.category.value}] {det.confidence:.2f}"
        origin = (x1, max(int(15 * scale), y1 - int(6 * scale)))
        cv2.putText(out, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.5 * scale, color, thick)
        # The point used for the distance estimate: where the object touches the floor.
        u, v = (int(c) for c in det.ground_pixel)
        cv2.circle(out, (u, v), int(4 * scale), (255, 0, 0), -1)
    return out


def describe(detections: list[Detection]) -> str:
    return ", ".join(f"{d.label}/{d.category.value} {d.confidence:.2f}" for d in detections) or "nothing"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image", nargs="+", help="image files to analyse")
    source.add_argument("--camera", type=int, help="webcam index for a live view in Rerun")
    parser.add_argument("--detector", choices=["floor", "open_vocab"], help="override perception.detector")
    parser.add_argument(
        "--classifier", choices=["none", "uniformity", "clip"], help="override perception.classifier"
    )
    parser.add_argument(
        "--ignore-top", type=float, help="floor detector: ignore this top fraction of the image"
    )
    parser.add_argument("--confidence", type=float, default=None, help="override perception.confidence")
    parser.add_argument("--clothing", nargs="+", help="try these words for clothing instead of the config's")
    parser.add_argument("--trash", nargs="+", help="try these words for trash instead of the config's")
    args = parser.parse_args()

    p = load_config()["perception"]
    p["detector"] = args.detector or p["detector"]
    p["classifier"] = args.classifier or p["classifier"]
    if args.ignore_top is not None:
        p["floor"]["ignore_top_fraction"] = args.ignore_top
    if args.confidence is not None:
        p["confidence"] = args.confidence
    p["prompts"] = {
        Category.CLOTHING: args.clothing or p["prompts"]["clothing"],
        Category.TRASH: args.trash or p["prompts"]["trash"],
    }
    detector = build_detector(p)
    print(f"Detector: {p['detector']}, classifier: {p['classifier']}")

    if args.image:
        out_dir = Path(REPO_ROOT) / "outputs" / "detect"
        out_dir.mkdir(parents=True, exist_ok=True)
        for path in args.image:
            bgr = cv2.imread(path)
            if bgr is None:
                print(f"{path}: cannot read")
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            start = time.perf_counter()
            detections = detector.detect(rgb)
            elapsed_ms = (time.perf_counter() - start) * 1000
            out = out_dir / f"{Path(path).stem}_detected.jpg"
            cv2.imwrite(str(out), cv2.cvtColor(annotate(rgb, detections), cv2.COLOR_RGB2BGR))
            print(f"{path}: {describe(detections)} ({elapsed_ms:.0f} ms) -> {out}")
        return

    import rerun as rr

    rr.init("makai_detect", spawn=True)
    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        raise SystemExit(f"Cannot open camera {args.camera} (macOS: allow camera access for your terminal).")
    print("Live view in Rerun. Ctrl-C to stop.")
    try:
        while True:
            ok, bgr = capture.read()
            if not ok:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            start = time.perf_counter()
            detections = detector.detect(rgb)
            elapsed_ms = (time.perf_counter() - start) * 1000
            rr.log("camera", rr.Image(annotate(rgb, detections)))
            rr.log("detections", rr.TextLog(f"{describe(detections)} ({elapsed_ms:.0f} ms)"))
    except KeyboardInterrupt:
        pass
    finally:
        capture.release()


if __name__ == "__main__":
    main()
