"""Web page to drive the base by hand from a phone, a tablet or a laptop, with no install.

The page (`drive_page.html`) sends the stick positions about 20 times per second to
`POST /api/drive` and gets back what to display. Standard library only (`http.server`), so
it runs in the Pi's LeRobot environment as is. Started by `scripts/drive.py`.

Endpoints, all JSON:
- `GET /api/info`: link, limits, wheel names;
- `GET /api/state`: telemetry, for a page that only watches;
- `POST /api/drive` {client, label, x, y, turn, speed, takeover}: stick input, see
  `ManualDriver.command`; answers the telemetry;
- `POST /api/stop`, `POST /api/release`: emergency stop and release, from any page;
- `POST /api/reset_odometry`;
- `POST /api/move` {client, axis, target, speed}: precise move (m or rad, m/s or rad/s),
  `POST /api/move/cancel`;
- `GET /api/camera/<name>.mjpg?fps=10`: live camera, as an MJPEG stream an <img> can show;
  `GET /api/camera/<name>.jpg` (`?download=1` to save it): the latest image;
- `GET /api/mission`: the sweeping mission (status, map, events) and its plan;
  `POST /api/mission/start`, `/stop`, `/reset` (simulation only). Only with a mission runner,
  i.e. through the host or in simulation: then `/` is the console (`console_page.html`) and
  the driving page moves to `/drive`;
- `GET /api/figures`: the figures of docs/figures and the training runs they come from;
  `GET /figures/<name>`: one of them;
- `GET /api/trials`, `GET /api/trials.csv`: the moves and their statistics;
  `POST /api/trials/measure` {id, tape}: what the tape says (cm, or degrees for turns);
  `POST /api/trials/clear`.

Refused requests answer {"error": "why"} with a 4xx status.
"""

from __future__ import annotations

import csv
import json
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from makai.robot.cameras import CameraHub
from makai.robot.manual import DriveLoop, ManualDriver
from makai.robot.moves import MoveSpec

PAGE = Path(__file__).with_name("drive_page.html")
CONSOLE = Path(__file__).with_name("console_page.html")
FIGURES = Path(__file__).resolve().parents[3] / "docs" / "figures"
MAX_BODY_BYTES = 4096
CAMERA_PATH = re.compile(r"^/api/camera/([A-Za-z0-9_-]+)\.(mjpg|jpg)$")
FIGURE_PATH = re.compile(r"^/figures/([A-Za-z0-9_-]+\.(png|jpg|csv))$")
FIGURE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "csv": "text/csv; charset=utf-8"}


def figures() -> dict[str, Any]:
    """The figures kept for the slides, and one line per training run found in their csv files."""
    if not FIGURES.is_dir():
        return {"images": [], "runs": []}
    images = sorted(p.name for p in FIGURES.iterdir() if p.suffix in (".png", ".jpg"))
    runs: dict[str, dict[str, Any]] = {}
    for path in sorted(FIGURES.glob("training_curves*.csv")):
        for row in csv.DictReader(path.open(newline="")):
            try:
                step, error = int(row["step"]), float(row["l1_loss"])
            except (KeyError, ValueError):
                continue
            run = runs.setdefault(row["run"], {"run": row["run"], "first": error, "steps": 0, "last": error})
            if step >= run["steps"]:
                run["steps"], run["last"], run["seconds_per_step"] = step, error, row.get("step_s")
    return {"images": images, "runs": list(runs.values())}


class DriveServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        loop: DriveLoop,
        driver: ManualDriver,
        info: dict[str, Any],
        cameras: CameraHub | None = None,
        runner: Any = None,
    ):
        super().__init__(address, DriveHandler)
        self.loop, self.driver, self.info = loop, driver, info
        self.runner = runner  # robot/autopilot.py MissionRunner, or None (wired mode on the Pi)
        self.cameras = cameras if cameras is not None else CameraHub()
        self.closing = threading.Event()  # ends the camera streams
        PAGE.read_bytes()  # fail now, not when the first phone connects

    def server_close(self) -> None:
        self.closing.set()
        super().server_close()

    @property
    def page(self) -> bytes:
        return PAGE.read_bytes()  # read each time: edit the page, reload the browser

    @property
    def console(self) -> bytes:
        return CONSOLE.read_bytes()

    def state(self, client: str | None) -> dict[str, Any]:
        return {**self.loop.snapshot(), **self.driver.status(client, time.monotonic())}


class DriveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive: one connection per page, not one per command
    server: DriveServer

    def do_GET(self) -> None:
        url = urlsplit(self.path)
        path, query = url.path, parse_qs(url.query)
        camera = CAMERA_PATH.match(path)
        if camera:
            name, kind = camera.groups()
            if name not in self.server.cameras.names:
                self._send(HTTPStatus.NOT_FOUND, b"no such camera", "text/plain")
            elif kind == "mjpg":
                self._stream(name, query)
            else:
                self._snapshot(name, query)
        elif path in ("/", "/index.html"):
            page = self.server.console if self.server.runner is not None else self.server.page
            self._send(HTTPStatus.OK, page, "text/html; charset=utf-8")
        elif path == "/drive":
            self._send(HTTPStatus.OK, self.server.page, "text/html; charset=utf-8")
        elif path == "/console":
            self._send(HTTPStatus.OK, self.server.console, "text/html; charset=utf-8")
        elif path == "/api/mission":
            if self.server.runner is None:
                self._error(
                    HTTPStatus.NOT_FOUND, "No mission here: start the page through the host, or with --sim."
                )
            else:
                self._json(self.server.runner.snapshot())
        elif path == "/api/figures":
            self._json(figures())
        elif FIGURE_PATH.match(path):
            name, kind = FIGURE_PATH.match(path).groups()
            file = FIGURES / name
            if file.is_file():
                self._send(HTTPStatus.OK, file.read_bytes(), FIGURE_TYPES[kind])
            else:
                self._send(HTTPStatus.NOT_FOUND, b"no such figure", "text/plain")
        elif path == "/api/info":
            self._json(self.server.info)
        elif path == "/api/state":
            self._json(self.server.state(None))
        elif path == "/api/trials":
            self._json(self.server.loop.trials.snapshot())
        elif path == "/api/trials.csv":
            body = self.server.loop.trials.csv_text().encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="move_trials.csv"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        body = self._read_json()
        if body is None:
            self._send(HTTPStatus.BAD_REQUEST, b"expected a small JSON object", "text/plain")
            return
        client = str(body.get("client", ""))[:64] or None
        driver = self.server.driver
        if path.startswith("/api/mission/"):
            self._mission(path.removeprefix("/api/mission/"))
            return
        if path == "/api/drive":
            if client is None:
                self._send(HTTPStatus.BAD_REQUEST, b"missing client id", "text/plain")
                return
            driver.command(
                client,
                body.get("x"),
                body.get("y"),
                body.get("turn"),
                body.get("speed"),
                time.monotonic(),
                takeover=body.get("takeover") is True,
                label=str(body.get("label", "")),
            )
        elif path == "/api/stop":
            driver.emergency_stop()
        elif path == "/api/release":
            driver.release()
        elif path == "/api/reset_odometry":
            if not self.server.loop.reset_odometry():
                self._error(HTTPStatus.CONFLICT, "Wait for the move to finish.")
                return
        elif path == "/api/move":
            if client is None:
                self._error(HTTPStatus.BAD_REQUEST, "missing client id")
                return
            try:
                spec = MoveSpec(str(body.get("axis")), float(body.get("target")), float(body.get("speed")))
            except (TypeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, f"Invalid move: {exc}")
                return
            try:
                self.server.loop.start_move(client or "", spec, time.monotonic(), str(body.get("label", "")))
            except ValueError as exc:
                self._error(HTTPStatus.CONFLICT, str(exc))
                return
        elif path == "/api/move/cancel":
            self.server.loop.cancel_move()
        elif path == "/api/trials/measure":
            try:
                tape = body.get("tape")
                self.server.loop.trials.measure(
                    int(body.get("id")), None if tape in (None, "") else float(tape)
                )
            except KeyError:
                self._error(HTTPStatus.NOT_FOUND, "No such move.")
                return
            except (TypeError, ValueError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc) or "invalid measurement")
                return
        elif path == "/api/trials/clear":
            self.server.loop.trials.clear()
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        self._json(self.server.state(client))

    def _mission(self, action: str) -> None:
        runner = self.server.runner
        if runner is None or action not in ("start", "stop", "reset"):
            self._error(
                HTTPStatus.NOT_FOUND, "No mission here: start the page through the host, or with --sim."
            )
            return
        try:
            getattr(runner, action)()
        except ValueError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        self._json(runner.snapshot())

    def _snapshot(self, name: str, query: dict[str, list[str]]) -> None:
        frame = self.server.cameras.jpeg(name)
        if frame is None:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, b"no image yet", "text/plain")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(frame[1])))
        self.send_header("Cache-Control", "no-store")
        if query.get("download"):
            stamp = time.strftime("%Y%m%d_%H%M%S")
            self.send_header("Content-Disposition", f'attachment; filename="{name}_{stamp}.jpg"')
        self.end_headers()
        self.wfile.write(frame[1])

    def _stream(self, name: str, query: dict[str, list[str]]) -> None:
        """Each new image as one part of a multipart response, at most `fps` per second."""
        try:
            fps = min(30.0, max(1.0, float(query.get("fps", ["10"])[0])))
        except ValueError:
            fps = 10.0
        hub = self.server.cameras
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        hub.watching(name, +1)
        last, next_time = 0, 0.0
        try:
            while not self.server.closing.is_set():
                frame = hub.wait_jpeg(name, last, timeout=1.0)
                if frame is None:
                    continue
                last, data = frame
                head = f"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: {len(data)}\r\n\r\n".encode()
                self.wfile.write(head + data + b"\r\n")  # a slow viewer blocks here and skips frames
                next_time = max(next_time + 1.0 / fps, time.monotonic())
                self.server.closing.wait(max(0.0, next_time - time.monotonic()))
        except OSError:
            pass  # the page closed the stream
        finally:
            hub.watching(name, -1)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # about 20 requests per second per open page: keep the terminal readable

    def _read_json(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            return None
        if length > MAX_BODY_BYTES:
            if length <= 1 << 20:
                self.rfile.read(length)  # drain it, so the connection stays usable
            else:
                self.close_connection = True  # the unread body would be taken for the next request
            return None
        if length <= 0:
            return None
        try:
            body = json.loads(self.rfile.read(length))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return body if isinstance(body, dict) else None

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status)

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
