"""The real `Perception`: front image -> objects and stations in the base frame."""

from __future__ import annotations

import math
from pathlib import Path

from makai.config import CONFIG_DIR
from makai.contracts import Category, Observation, Scene, Target
from makai.perception.detector import Detector
from makai.perception.geometry import CameraModel, GroundPlane
from makai.perception.stations import StationDetector


class CameraPerception:
    def __init__(
        self,
        detector: Detector,
        ground: GroundPlane,
        stations: StationDetector | None = None,
        camera: str = "front",
        max_range_m: float = 2.5,
    ):
        self.detector, self.ground, self.stations = detector, ground, stations
        self.camera, self.max_range_m = camera, max_range_m
        self.detections = []  # last raw detections, for visualisation

    def perceive(self, obs: Observation) -> Scene:
        image = obs.images.get(self.camera)
        if image is None:
            return Scene()
        self.detections = self.detector.detect(image)
        targets = []
        for det in self.detections:
            x, y = self.ground.pixel_to_ground(*det.ground_pixel)
            # Points above the horizon project behind the robot or very far: drop them.
            if x > 0 and math.hypot(x, y) <= self.max_range_m:
                targets.append(Target(det.category, det.label, x, y, det.confidence))
        stations = self.stations.detect(image) if self.stations else {}
        return Scene(tuple(targets), stations)


def build_perception(cfg: dict) -> CameraPerception:
    from makai.perception.detector import OpenVocabDetector

    p = cfg["perception"]
    camera = CameraModel(**p["camera_model"])
    ground_file = Path(CONFIG_DIR) / p["ground_plane_file"]
    # Calibrated homography if it exists, otherwise the approximate camera model.
    ground = GroundPlane.load(ground_file) if ground_file.exists() else camera.ground_plane()
    stations = StationDetector(
        camera,
        {int(marker_id): Category(category) for marker_id, category in p["stations"]["marker_ids"].items()},
        p["stations"]["marker_size_m"],
    )
    detector = OpenVocabDetector(
        p["prompts"], model=p["model"], confidence=p["confidence"], device=p.get("device")
    )
    return CameraPerception(detector, ground, stations, max_range_m=p["max_range_m"])
