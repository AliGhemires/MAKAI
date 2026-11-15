"""Live camera images for the control page.

`CameraHub` keeps the latest image of each camera and encodes it to JPEG once, however many
pages watch it. Images come from one of:
- the robot's observations, through the host (`DriveLoop` puts them in the hub);
- `CameraCapture`: the camera opened directly with OpenCV, on the Pi in wired mode;
- `SimCamera`: a synthetic view of the simulated floor, to try the page without a robot.

Images are stored as they come (RGB from LeRobot, BGR from OpenCV) and converted when encoded.
"""

from __future__ import annotations

import logging
import math
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)
STALE_S = 2.0  # no new image for this long: the camera is shown as lost


@dataclass
class _Camera:
    frame_id: int = 0
    image: np.ndarray | None = None
    rgb: bool = False
    stamp: float = 0.0
    jpeg: bytes | None = None
    jpeg_id: int = -1
    fps: float = 0.0
    error: str | None = "waiting for the first image"
    source: str = ""
    viewers: int = 0
    _history: list[float] = field(default_factory=list)


class CameraHub:
    """Latest image of each camera, shared by every viewer. Thread-safe."""

    def __init__(self, quality: int = 70, clock: Callable[[], float] = time.monotonic):
        self.quality = quality
        self.clock = clock
        self._cond = threading.Condition()
        self._cameras: dict[str, _Camera] = {}

    def expect(self, name: str, source: str = "") -> None:
        """Announce a camera before its first image, so the page can say it is waited for."""
        with self._cond:
            self._cameras.setdefault(name, _Camera()).source = source

    @property
    def names(self) -> list[str]:
        with self._cond:
            return list(self._cameras)

    def put(self, name: str, image: np.ndarray, rgb: bool) -> None:
        now = self.clock()
        with self._cond:
            cam = self._cameras.setdefault(name, _Camera())
            cam.frame_id += 1
            cam.image, cam.rgb, cam.stamp, cam.error = image, rgb, now, None
            cam._history = [t for t in cam._history if now - t < 2.0] + [now]
            span = cam._history[-1] - cam._history[0]
            cam.fps = (len(cam._history) - 1) / span if span > 0 else 0.0
            self._cond.notify_all()

    def fail(self, name: str, message: str) -> None:
        with self._cond:
            cam = self._cameras.setdefault(name, _Camera())
            if cam.error != message:
                log.warning("camera %s: %s", name, message)
            cam.error = message
            self._cond.notify_all()

    def jpeg(self, name: str) -> tuple[int, bytes] | None:
        """Latest image as JPEG, with its frame number. None before the first image."""
        with self._cond:
            cam = self._cameras.get(name)
            if cam is None or cam.image is None:
                return None
            if cam.jpeg_id == cam.frame_id:
                return cam.frame_id, cam.jpeg
            frame_id, image, rgb = cam.frame_id, cam.image, cam.rgb
        bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if rgb else image  # encoding outside the lock
        ok, buffer = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        if not ok:
            return None
        data = buffer.tobytes()
        with self._cond:
            if cam.frame_id == frame_id:
                cam.jpeg, cam.jpeg_id = data, frame_id
        return frame_id, data

    def wait_jpeg(self, name: str, after: int, timeout: float) -> tuple[int, bytes] | None:
        """Wait for an image newer than frame `after`; None on timeout."""
        with self._cond:
            fresh = self._cond.wait_for(
                lambda: (cam := self._cameras.get(name)) is not None and cam.frame_id > after, timeout
            )
        return self.jpeg(name) if fresh else None

    def watching(self, name: str, delta: int) -> None:
        with self._cond:
            cam = self._cameras.setdefault(name, _Camera())
            cam.viewers = max(0, cam.viewers + delta)

    def status(self) -> dict[str, dict[str, Any]]:
        now = self.clock()
        with self._cond:
            out = {}
            for name, cam in self._cameras.items():
                age = now - cam.stamp if cam.image is not None else None
                error = cam.error or (
                    f"no new image for {age:.0f} s" if age is not None and age > STALE_S else None
                )
                out[name] = {
                    "ok": error is None,
                    "error": error,
                    "fps": round(cam.fps, 1) if error is None else 0.0,
                    "width": None if cam.image is None else int(cam.image.shape[1]),
                    "height": None if cam.image is None else int(cam.image.shape[0]),
                    "source": cam.source,
                    "viewers": cam.viewers,
                }
            return out


def open_capture(source: int | str, width: int, height: int, fps: int) -> cv2.VideoCapture | None:
    """Open a USB camera with OpenCV; MJPG keeps two cameras within the USB bandwidth."""
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    cap = cv2.VideoCapture(source, backend)
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


class CameraCapture(threading.Thread):
    """Reads one camera into the hub; reopens it if it is unplugged and plugged back."""

    def __init__(
        self, hub: CameraHub, name: str, source: int | str, width=640, height=480, fps=15, max_fps=10.0
    ):
        super().__init__(name=f"camera-{name}", daemon=True)
        self.hub, self.cam, self.source = hub, name, source
        self.width, self.height, self.fps, self.max_fps = width, height, fps, max_fps
        self._stop = threading.Event()
        hub.expect(name, str(source))

    def run(self) -> None:
        while not self._stop.is_set():
            cap = open_capture(self.source, self.width, self.height, self.fps)
            if cap is None:
                self.hub.fail(self.cam, f"cannot open {self.source}: not plugged in, or used by the host?")
                self._stop.wait(3.0)
                continue
            last = 0.0
            try:
                while not self._stop.is_set():
                    ok, frame = cap.read()  # waits for the camera: keeps its pace
                    if not ok or frame is None:
                        self.hub.fail(self.cam, f"{self.source} stopped sending images (unplugged?)")
                        break
                    now = time.monotonic()
                    if now - last >= 1.0 / self.max_fps:
                        last = now
                        self.hub.put(self.cam, frame, rgb=False)
            finally:
                cap.release()
            self._stop.wait(1.0)

    def stop(self) -> None:
        self._stop.set()


class SimCamera(threading.Thread):
    """A synthetic camera for the simulator: the floor grid seen from the robot, moving with it."""

    def __init__(
        self,
        hub: CameraHub,
        name: str,
        pose: Callable[[], tuple[float, float, float]],
        fps=10.0,
        things: Callable[[], list[tuple[float, float, tuple[int, int, int], float]]] | None = None,
    ):
        super().__init__(name=f"sim-camera-{name}", daemon=True)
        self.hub, self.cam, self.pose, self.period = hub, name, pose, 1.0 / fps
        self.things = things  # what lies on the simulated floor: (x, y, colour BGR, radius in metres)
        self._stop = threading.Event()
        hub.expect(name, "simulation")

    def run(self) -> None:
        while not self._stop.wait(self.period):
            things = self.things() if self.things is not None else ()
            self.hub.put(self.cam, render_floor(self.cam, *self.pose(), things=things), rgb=False)

    def stop(self) -> None:
        self._stop.set()


def render_floor(name: str, x: float, y: float, yaw: float, width=640, height=480, things=()) -> np.ndarray:
    """A 25 cm floor grid in perspective, as a camera 25 cm above the floor would see it, with
    the `things` that lie on it: (x, y, colour BGR, radius in metres), drawn as discs."""
    img = np.full((height, width, 3), (58, 52, 46), np.uint8)
    horizon, focal, cam_height = int(height * 0.32), 520.0, 0.25 if name != "wrist" else 0.12
    img[:horizon] = (92, 80, 70)
    c, s = math.cos(yaw), math.sin(yaw)

    def project(wx: float, wy: float) -> tuple[int, int] | None:
        dx, dy = wx - x, wy - y
        forward, left = c * dx + s * dy, -s * dx + c * dy
        if forward < 0.12:
            return None
        return int(width / 2 - focal * left / forward), int(horizon + focal * cam_height / forward)

    step, reach = 0.25, 3.0
    x0, y0 = math.floor((x - reach) / step) * step, math.floor((y - reach) / step) * step
    lines = [((x0 + i * step, y0), (x0 + i * step, y0 + 2 * reach)) for i in range(int(2 * reach / step) + 1)]
    lines += [
        ((x0, y0 + i * step), (x0 + 2 * reach, y0 + i * step)) for i in range(int(2 * reach / step) + 1)
    ]
    for (ax, ay), (bx, by) in lines:
        points = [project(ax + (bx - ax) * k / 24, ay + (by - ay) * k / 24) for k in range(25)]
        for p, q in zip(points, points[1:], strict=False):
            if p and q:
                cv2.line(img, p, q, (120, 112, 104), 1, cv2.LINE_AA)
    origin = project(0.0, 0.0)
    if origin:
        cv2.circle(img, origin, 6, (60, 180, 250), -1, cv2.LINE_AA)
    for wx, wy, colour, radius in sorted(
        things, key=lambda t: -math.hypot(t[0] - x, t[1] - y)
    ):  # far ones first
        centre = project(wx, wy)
        forward = c * (wx - x) + s * (wy - y)
        if centre and forward > 0.15:
            half = max(2, int(focal * radius / forward))
            cv2.ellipse(
                img,
                (centre[0], centre[1] - half // 3),
                (half, max(2, half // 2)),
                0,
                0,
                360,
                colour,
                -1,
                cv2.LINE_AA,
            )
    cv2.putText(
        img, f"{name} (simulated)", (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (235, 235, 235), 1, cv2.LINE_AA
    )
    stamp = f"x {x:+.2f} m  y {y:+.2f} m  {math.degrees(yaw):+.0f} deg"
    cv2.putText(
        img, stamp, (14, height - 16), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1, cv2.LINE_AA
    )
    return img
