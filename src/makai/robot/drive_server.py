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
- `POST /api/reset_odometry`.
"""

from __future__ import annotations

import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from makai.robot.manual import DriveLoop, ManualDriver

PAGE = Path(__file__).with_name("drive_page.html")
MAX_BODY_BYTES = 4096


class DriveServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], loop: DriveLoop, driver: ManualDriver, info: dict[str, Any]):
        super().__init__(address, DriveHandler)
        self.loop, self.driver, self.info = loop, driver, info
        PAGE.read_bytes()  # fail now, not when the first phone connects

    @property
    def page(self) -> bytes:
        return PAGE.read_bytes()  # read each time: edit the page, reload the browser

    def state(self, client: str | None) -> dict[str, Any]:
        return {**self.loop.snapshot(), **self.driver.status(client, time.monotonic())}


class DriveHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive: one connection per page, not one per command
    server: DriveServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, self.server.page, "text/html; charset=utf-8")
        elif path == "/api/info":
            self._json(self.server.info)
        elif path == "/api/state":
            self._json(self.server.state(None))
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
            self.server.loop.reset_odometry()
        else:
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")
            return
        self._json(self.server.state(client))

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

    def _json(self, payload: dict[str, Any]) -> None:
        self._send(HTTPStatus.OK, json.dumps(payload).encode(), "application/json")

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
