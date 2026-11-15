"""The real `Perception`: front image -> objects and stations in the base frame."""

from __future__ import annotations

import math
from pathlib import Path

from makai.config import CONFIG_DIR
from makai.contracts import Category, Detection, Observation, Scene, Target
from makai.perception.detector import Detector
from makai.perception.geometry import CameraModel, GroundPlane
from makai.perception.stations import StationDetector, TapeStationDetector, build_station_detector

CUT_MARGIN_PX = 3  # a box ending this close to the bottom row is cut by the image


class CameraPerception:
    def __init__(
        self,
        detector: Detector,
        ground: GroundPlane,
        stations: StationDetector | TapeStationDetector | None = None,
        camera: str = "front",
        max_range_m: float = 2.5,
        min_size_m: float | None = None,
        max_size_m: float | None = None,
    ):
        self.detector, self.ground, self.stations = detector, ground, stations
        self.camera, self.max_range_m = camera, max_range_m
        self.min_size_m, self.max_size_m = min_size_m, max_size_m
        self.detections = []  # last raw detections, for visualisation

    def perceive(self, obs: Observation) -> Scene:
        image = obs.images.get(self.camera)
        if image is None:
            return Scene()
        self.detections = self.detector.detect(image)
        targets = []
        for det in self.detections:
            # A box cut by the bottom of the image shows an object that goes on below it: its
            # lowest visible point is not where it touches the floor, and the distance read
            # there would be too long. The mission finishes such an approach on odometry.
            if det.bbox_xyxy[3] >= image.shape[0] - CUT_MARGIN_PX:
                continue
            x, y = self.ground.pixel_to_ground(*det.ground_pixel)
            # Points above the horizon project behind the robot or very far: drop them.
            if x > 0 and math.hypot(x, y) <= self.max_range_m and self._plausible_size(det):
                targets.append(Target(det.category, det.label, x, y, det.confidence))
        stations = self.stations.detect(image) if self.stations else {}
        return Scene(tuple(targets), stations)

    def _plausible_size(self, det: Detection) -> bool:
        """Width of the object on the floor, in metres: rejects specks and furniture."""
        if self.min_size_m is None and self.max_size_m is None:
            return True
        x1, _, x2, y2 = det.bbox_xyxy
        left, right = self.ground.pixel_to_ground(x1, y2), self.ground.pixel_to_ground(x2, y2)
        width = math.hypot(left[0] - right[0], left[1] - right[1])
        return (self.min_size_m or 0.0) <= width <= (self.max_size_m or math.inf)


def build_detector(p: dict) -> Detector:
    """The object detector chosen by `perception.detector` in the config."""
    if p.get("detector", "floor") == "learned":
        from makai.perception.detector import LearnedDetector

        learned = p["learned"]
        return LearnedDetector(learned["weights"], learned["confidence"], p.get("device"))
    if p["detector"] == "open_vocab":
        from makai.perception.detector import OpenVocabDetector

        return OpenVocabDetector(
            p["prompts"], model=p["model"], confidence=p["confidence"], device=p.get("device")
        )

    from makai.perception.floor import FloorBlobDetector, FloorColor

    f = p["floor"]
    floor = FloorColor(**f["color"])
    classifier = None
    if p.get("classifier", "none") == "uniformity":
        from makai.perception.classify import UniformityClassifier

        classifier = UniformityClassifier(floor, **p["uniformity"])
    elif p["classifier"] == "clip":
        from makai.perception.classify import ClipClassifier

        c = p["clip"]
        classifier = ClipClassifier(c["clothing"], c["other"], model=c["model"], device=p.get("device"))
    return FloorBlobDetector(
        floor,
        classifier,
        default_category=Category(f["default_category"]),
        ignore_top_fraction=f["ignore_top_fraction"],
    )


def build_perception(cfg: dict) -> CameraPerception:
    p = cfg["perception"]
    camera = CameraModel(**p["camera_model"])
    ground_file = Path(CONFIG_DIR) / p["ground_plane_file"]
    # Calibrated homography if it exists, otherwise the approximate camera model.
    ground = GroundPlane.load(ground_file) if ground_file.exists() else camera.ground_plane()
    stations = build_station_detector(p, camera)  # tape strips or ArUco markers
    return CameraPerception(
        build_detector(p),
        ground,
        stations,
        max_range_m=p["max_range_m"],
        min_size_m=p["floor"]["min_size_m"],
        max_size_m=p["floor"]["max_size_m"],
    )
