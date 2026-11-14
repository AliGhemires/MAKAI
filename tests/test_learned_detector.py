"""Our trained detector, on two real evening-light frames it was not trained on.

Skipped where Ultralytics is not installed (CI installs the core only): run `make check`
locally after `make setup` to exercise it.
"""

from pathlib import Path

import cv2
import pytest

pytest.importorskip("ultralytics")

from makai.config import load_config  # noqa: E402
from makai.contracts import Category  # noqa: E402
from makai.perception.detector import LearnedDetector  # noqa: E402
from makai.perception.lighting import LIGHTINGS  # noqa: E402
from makai.perception.pipeline import build_detector  # noqa: E402

SAMPLES = {"evening_sock.jpg": Category.CLOTHING, "evening_can.jpg": Category.TRASH}


@pytest.fixture(scope="module")
def detector():
    perception = load_config()["perception"]
    assert perception["detector"] == "learned"
    built = build_detector(perception)
    assert isinstance(built, LearnedDetector)
    assert built.device in ("cuda", "mps", "cpu")
    return built


def load(name: str):
    return cv2.cvtColor(cv2.imread(str(Path(__file__).parent / "samples" / name)), cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize("name", SAMPLES)
def test_finds_the_object_and_its_category_under_evening_light(detector, name):
    detections = detector.detect(load(name))
    assert [d.category for d in detections] == [SAMPLES[name]]


def test_holds_up_when_the_light_changes(detector):
    right = total = 0
    for name, category in SAMPLES.items():
        image = load(name)
        for relight in LIGHTINGS.values():
            detections = detector.detect(relight(image))
            right += [d.category for d in detections] == [category]
            total += 1
    assert right / total >= 0.9, f"only {right}/{total} right under changed lighting"


def test_missing_weights_give_a_clear_error():
    with pytest.raises(FileNotFoundError, match="weights not found"):
        LearnedDetector("models/does_not_exist.pt")
