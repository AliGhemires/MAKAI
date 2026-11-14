"""Floor-colour object detection, on synthetic images (no model, no hardware)."""

import cv2
import numpy as np
import pytest

from makai.contracts import Category, Observation
from makai.perception.classify import UniformityClassifier
from makai.perception.floor import FloorBlobDetector, FloorColor
from makai.perception.geometry import CameraModel
from makai.perception.pipeline import CameraPerception, build_detector

W, H = 640, 480


def carpet(value: int = 170) -> np.ndarray:
    """An orange carpet with some texture; `value` sets how bright (lit or in shadow)."""
    rng = np.random.default_rng(0)
    hsv = np.zeros((H, W, 3), dtype=np.uint8)
    hsv[..., 0] = rng.integers(8, 18, (H, W))
    hsv[..., 1] = rng.integers(140, 200, (H, W))
    hsv[..., 2] = np.clip(value + rng.integers(-15, 15, (H, W)), 0, 255)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)


def with_object(image: np.ndarray, centre=(320, 300), axes=(45, 25), colour=(15, 15, 18)) -> np.ndarray:
    out = image.copy()
    cv2.ellipse(out, centre, axes, 0, 0, 360, colour, -1)
    return out


def test_empty_floor_gives_nothing():
    assert FloorBlobDetector().detect(carpet()) == []


def test_shadow_and_sunlight_are_still_floor():
    image = carpet()
    image[:, : W // 3] = carpet(value=70)[:, : W // 3]  # deep shadow
    image[:, 2 * W // 3 :] = carpet(value=235)[:, 2 * W // 3 :]  # sunlit band
    assert FloorBlobDetector().detect(image) == []


@pytest.mark.parametrize("colour", [(15, 15, 18), (240, 240, 235), (40, 90, 200)])
def test_finds_an_object_that_is_not_floor_coloured(colour):
    detections = FloorBlobDetector().detect(with_object(carpet(), colour=colour))
    assert len(detections) == 1
    x1, y1, x2, y2 = detections[0].bbox_xyxy
    assert (x1, y1, x2, y2) == pytest.approx((275, 275, 365, 325), abs=6)
    assert detections[0].category is Category.CLOTHING  # the default when there is no classifier


def test_floor_coloured_object_is_invisible():
    """Documented limit: demo objects must contrast with the carpet."""
    assert FloorBlobDetector().detect(with_object(carpet(), colour=(200, 110, 50))) == []


def test_ignores_specks_huge_areas_and_the_top_band():
    image = with_object(carpet(), centre=(100, 400), axes=(4, 3))  # speck
    image[:, :300] = 20  # a wall of dark pixels: far too big to be an object
    image = with_object(image, centre=(500, 40), axes=(40, 25))  # clutter at the top of the image
    assert len(FloorBlobDetector().detect(image)) == 1
    assert FloorBlobDetector(ignore_top_fraction=0.2).detect(image) == []


def test_classifier_decides_the_category():
    class Stub:
        def classify(self, crop_rgb):
            self.crop = crop_rgb
            return Category.TRASH, 0.8

    stub = Stub()
    detection = FloorBlobDetector(classifier=stub).detect(with_object(carpet()))[0]
    assert (detection.category, detection.confidence) == (Category.TRASH, 0.8)
    assert 90 < stub.crop.shape[1] < 140 and 50 < stub.crop.shape[0] < 100  # tight crop with a margin


def test_perception_keeps_only_objects_of_plausible_size():
    camera = CameraModel(width=W, height=H, hfov_deg=46, height_m=0.20, pitch_deg=30)
    ground = camera.ground_plane()
    # A 10 cm wide object 50 cm ahead, and a 70 cm wide one at the same distance.
    small = [ground.ground_to_pixel(0.5, y) for y in (0.05, -0.05)]
    big = [ground.ground_to_pixel(0.5, y) for y in (0.35, -0.35)]

    def scene(left, right):
        image = carpet()
        cv2.rectangle(
            image, (int(left[0]), int(left[1]) - 30), (int(right[0]), int(left[1])), (15, 15, 18), -1
        )
        perception = CameraPerception(FloorBlobDetector(), ground, min_size_m=0.03, max_size_m=0.35)
        return perception.perceive(Observation(stamp=0.0, images={"front": image}))

    targets = scene(*small).targets
    assert len(targets) == 1
    assert (targets[0].x_m, targets[0].y_m) == pytest.approx((0.5, 0.0), abs=0.02)
    assert scene(*big).targets == ()


def printed(image: np.ndarray, centre=(320, 300), axes=(60, 34)) -> np.ndarray:
    """A bright object covered with dark print, like a drink can."""
    out = with_object(image, centre=centre, axes=axes, colour=(235, 235, 240))
    for x in range(centre[0] - axes[0] + 8, centre[0] + axes[0] - 8, 9):
        cv2.line(out, (x, centre[1] - 16), (x + 5, centre[1] + 16), (25, 40, 150), 3)
    return out


def test_uniformity_classifier_tells_plain_fabric_from_printed_packaging():
    detector = FloorBlobDetector(classifier=UniformityClassifier())
    sock = detector.detect(with_object(carpet(), axes=(60, 34)))[0]
    can = detector.detect(printed(carpet()))[0]
    assert sock.category is Category.CLOTHING and sock.confidence > 0.5
    assert can.category is Category.TRASH and can.confidence > 0.5


def test_object_too_small_to_classify_is_reported_as_a_guess():
    detector = FloorBlobDetector(classifier=UniformityClassifier(), default_category=Category.CLOTHING)
    far_can = detector.detect(printed(carpet(), axes=(18, 11)))
    assert len(far_can) == 1
    assert (far_can[0].category, far_can[0].confidence) == (Category.CLOTHING, 0.0)


def test_floor_detector_is_built_from_the_shared_config():
    from makai.config import load_config

    perception = load_config()["perception"]
    perception["detector"] = "floor"  # the fallback detector, still built from the same config
    assert perception["classifier"] == "uniformity"
    detector = build_detector(perception)
    assert isinstance(detector, FloorBlobDetector) and isinstance(detector.classifier, UniformityClassifier)
    assert detector.floor == FloorColor(**perception["floor"]["color"])
    assert detector.detect(with_object(carpet(), axes=(60, 34)))[0].category is Category.CLOTHING
    assert detector.detect(printed(carpet()))[0].category is Category.TRASH
