"""Train our own object detector from folders of images, with no manual annotation.

    uv run python scripts/train_detector.py --name v2 \\
        --clothing data/test_frames/IMG_1378 --trash data/test_frames/IMG_1377

Each folder holds images showing ONE object of that category (frames of a short video shot
around the object are ideal; see scripts/eval_frames.py for the ffmpeg line). `--empty`
folders show the floor with nothing to pick up.

How the boxes are obtained (`--labeller`):
- a previous version of the detector (default: the one in configs/makai.yaml). Images where it
  does not find exactly one object of the expected category are left out, never guessed;
- `floor`: the floor-colour detector, for the very first model, on daylight images only.
- no model at all, for an image that comes with its empty twin: next to `name.jpg`, a file
  `name_empty.jpg` taken from the same place with the object removed. The box is what differs
  between the two (`makai.perception.autolabel`), and the empty image is used as an example of
  a floor with nothing on it. The recorded pick episodes give such pairs for free: first image
  of the front camera (object on the floor), last image (object picked up).
Check a sample of the boxes by eye before trusting a model trained on them.

Each training image is also copied under random lightings and shadows, which is what makes the
detector hold up when the light changes. Every 4th block of 6 images is kept out of training
and used for the score printed at the end. The weights go to models/detector_<name>.pt: point
`perception.learned.weights` at them and commit the file (a few MB).

About 10 minutes on an Apple Silicon laptop for 300 images.
"""

from __future__ import annotations

import argparse
import collections
import shutil
from pathlib import Path

import cv2
import numpy as np
import yaml

from makai.config import REPO_ROOT, load_config
from makai.contracts import Category
from makai.perception.autolabel import box_by_difference
from makai.perception.lighting import random_relight
from makai.perception.pipeline import build_detector

CLASSES = {Category.CLOTHING: 0, Category.TRASH: 1}
IMAGES = (".jpg", ".jpeg", ".png")


def write_example(root: Path, split: str, stem: str, image_rgb: np.ndarray, boxes: list) -> None:
    (root / "images" / split).mkdir(parents=True, exist_ok=True)
    (root / "labels" / split).mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(root / "images" / split / f"{stem}.jpg"), cv2.cvtColor(image_rgb, cv2.COLOR_RGB2BGR))
    height, width = image_rgb.shape[:2]
    lines = [
        f"{cls} {(x1 + x2) / 2 / width:.5f} {(y1 + y2) / 2 / height:.5f} {(x2 - x1) / width:.5f} {(y2 - y1) / height:.5f}"
        for (x1, y1, x2, y2), cls in boxes
    ]
    (root / "labels" / split / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", required=True, help="version name: weights go to models/detector_<name>.pt")
    parser.add_argument("--clothing", nargs="*", default=[])
    parser.add_argument("--trash", nargs="*", default=[])
    parser.add_argument("--empty", nargs="*", default=[])
    parser.add_argument(
        "--labeller", default="learned", help="'learned' (current detector), 'floor', or weights path"
    )
    parser.add_argument("--label-confidence", type=float, default=0.4)
    parser.add_argument("--copies", type=int, default=2, help="re-lit copies of each training image")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--device", default="mps", help="mps (Mac), cuda, or cpu")
    parser.add_argument("--base", default="yolo11n.pt", help="pretrained model to start from")
    args = parser.parse_args()

    p = load_config()["perception"]
    if args.labeller == "floor":
        p["detector"], p["classifier"] = "floor", "none"
    else:
        p["detector"] = "learned"
        p["learned"]["confidence"] = args.label_confidence
        if args.labeller != "learned":
            p["learned"]["weights"] = args.labeller
    labeller = build_detector(p)

    root = REPO_ROOT / "outputs" / "detector" / args.name
    shutil.rmtree(root, ignore_errors=True)
    rng = np.random.default_rng(0)
    stats = collections.Counter()
    held_out: list[tuple[Path, Category | None]] = []
    folders = [(f, Category.CLOTHING) for f in args.clothing] + [(f, Category.TRASH) for f in args.trash]
    folders += [(f, None) for f in args.empty]
    for folder, truth in folders:
        files = [
            f
            for f in sorted(Path(folder).iterdir())
            if f.suffix.lower() in IMAGES and not f.stem.endswith("_empty")
        ]
        for index, path in enumerate(files):
            image = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
            split = "val" if (index // 6) % 4 == 3 else "train"
            if split == "val":
                held_out.append((path, truth))
            boxes = []
            twin = path.with_name(f"{path.stem}_empty{path.suffix}")
            stem = f"{Path(folder).name}_{path.stem}"
            if truth is not None and twin.exists():  # labelled by what changed since the floor was empty
                empty = cv2.cvtColor(cv2.imread(str(twin)), cv2.COLOR_BGR2RGB)
                box = box_by_difference(image, empty, min_area_px=int(0.02 * image.shape[0] * image.shape[1]))
                if box is None:
                    stats["left out (the two images do not differ by one object)"] += 1
                    continue
                boxes = [(box, CLASSES[truth])]
                stats["labelled by difference"] += 1
                write_example(root, split, f"{stem}_empty", empty, [])
                if split == "val":
                    held_out.append((twin, None))
            elif truth is not None:
                found = labeller.detect(image)
                if args.labeller == "floor":  # no classifier: keep the biggest blob
                    found = sorted(
                        found,
                        key=lambda d: -(d.bbox_xyxy[2] - d.bbox_xyxy[0]) * (d.bbox_xyxy[3] - d.bbox_xyxy[1]),
                    )[:1]
                else:
                    found = [d for d in found if d.category is truth]
                if len(found) != 1:
                    stats["left out (no single confident box)"] += 1
                    continue
                boxes = [(found[0].bbox_xyxy, CLASSES[truth])]
            write_example(root, split, stem, image, boxes)
            stats[split] += 1
            if split == "train":
                for copy in range(args.copies):
                    write_example(root, split, f"{stem}_relit{copy}", random_relight(image, rng), boxes)
    print("images:", dict(stats))
    if not stats["train"] or not stats["val"]:
        raise SystemExit("Not enough labelled images to train: check the folders and the labeller.")
    data = {
        "path": str(root),
        "train": "images/train",
        "val": "images/val",
        "names": {v: k.value for k, v in CLASSES.items()},
    }
    (root / "data.yaml").write_text(yaml.safe_dump(data))

    from ultralytics import YOLO

    YOLO(args.base).train(
        data=str(root / "data.yaml"), epochs=args.epochs, imgsz=640, batch=32, device=args.device, workers=6,
        hsv_h=0.02, hsv_s=0.6, hsv_v=0.5, degrees=10, scale=0.6, fliplr=0.5,
        project=str(root), name="run", exist_ok=True, verbose=False, plots=False,
    )  # fmt: skip
    weights = REPO_ROOT / "models" / f"detector_{args.name}.pt"
    weights.parent.mkdir(exist_ok=True)
    shutil.copy(root / "run" / "weights" / "best.pt", weights)

    # Score on the held-out images, including those the labeller could not label.
    p["detector"] = "learned"
    p["learned"] = {
        "weights": str(weights),
        "confidence": load_config()["perception"]["learned"]["confidence"],
    }
    detector = build_detector(p)
    outcome = collections.Counter()
    for path, truth in held_out:
        detections = detector.detect(cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB))
        right = sum(d.category is truth for d in detections)
        ok = not detections if truth is None else (right, len(detections) - right) == (1, 0)
        outcome["ok" if ok else "nothing found" if not detections else "wrong"] += 1
    print(f"held-out images (never trained on): {dict(outcome)} of {len(held_out)}")
    print(
        f"weights: {weights.relative_to(REPO_ROOT)}  -> set perception.learned.weights to this path and commit it"
    )


if __name__ == "__main__":
    main()
