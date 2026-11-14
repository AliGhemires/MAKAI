"""Drive the LeKiwi base from a web page, on a phone, a tablet or a laptop of the same network.

On the Pi, motor board on its USB (works without the arm), in the `lerobot` conda env:

    cd ~/MAKAI && python scripts/drive.py --link wired

then open http://lekiwi.local:8000 (or http://<Pi IP>:8000). Start it inside `tmux`: closing
the SSH session stops the robot and the page otherwise.

Through the host (arm mounted, host running on the Pi), from a laptop:

    uv run python scripts/drive.py --link host        # then http://localhost:8000

Without a robot, to try the page:

    uv run python scripts/drive.py --sim
"""

from __future__ import annotations

import argparse
import logging
import signal
import socket
from dataclasses import asdict

from makai.config import load_config
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import LINKS, BaseGeometry, LeKiwiRobot
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver

TELEMETRY_HZ = 10.0
log = logging.getLogger("drive")


def lan_address() -> str | None:
    """This machine's address on the network (no packet is sent: it only picks the interface)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def _interrupt(signum, frame) -> None:
    raise KeyboardInterrupt  # same clean stop as Ctrl+C: wheels stopped, serial port released


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    where = parser.add_mutually_exclusive_group()
    where.add_argument(
        "--link", choices=LINKS, help="how to reach the wheels (default: robot.link in the config)"
    )
    where.add_argument("--sim", action="store_true", help="no robot: drive a simulated base")
    parser.add_argument("--serial-port", help="motor board port in wired mode (default: robot.base.port)")
    parser.add_argument("--http-port", type=int, help="port of the page (default: teleop.drive.http_port)")
    parser.add_argument("--bind", default="0.0.0.0", help="listen address; 127.0.0.1 = this machine only")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    cfg = load_config()
    drive_cfg = cfg["teleop"]["drive"]
    limits = DriveLimits.from_config(drive_cfg)
    geometry = BaseGeometry.from_config(cfg["robot"]["base"])
    if args.sim:
        from makai.sim.world import SimRobot, SimWorld

        robot, link, serial_port = SimRobot(SimWorld(), dt=1 / TELEMETRY_HZ), "sim", None
    else:
        link = args.link or cfg["robot"].get("link", "host")
        if args.serial_port:
            cfg["robot"]["base"]["port"] = args.serial_port
        serial_port = cfg["robot"]["base"]["port"] if link == "wired" else None
        robot = LeKiwiRobot.from_config(cfg, link=link)

    driver = ManualDriver(limits)
    loop = DriveLoop(robot, driver, geometry, telemetry_hz=TELEMETRY_HZ)
    info = {
        "link": link,
        "serial_port": serial_port,
        "limits": asdict(limits),
        "wheels": [name.removeprefix("base_").removesuffix("_wheel") for name in geometry.names],
    }
    http_port = args.http_port or int(drive_cfg.get("http_port", 8000))
    try:  # before touching the robot: a busy port should not leave the wheels armed
        server = DriveServer((args.bind, http_port), loop, driver, info)
    except OSError as exc:
        parser.exit(1, f"cannot listen on port {http_port} ({exc}). Already running? Try --http-port.\n")

    signal.signal(signal.SIGTERM, _interrupt)
    if hasattr(signal, "SIGHUP"):  # the SSH session that started us is gone
        signal.signal(signal.SIGHUP, _interrupt)

    log.info("connecting to the robot (%s%s)", link, f", {serial_port}" if serial_port else "")
    try:
        robot.connect()
    except BaseException:
        server.server_close()
        raise
    loop.start()
    urls = [f"http://localhost:{http_port}"]
    if args.bind != "127.0.0.1":
        address = lan_address()
        urls += [f"http://{address}:{http_port}"] if address else []
        urls += [f"http://{socket.gethostname()}.local:{http_port}"]
    log.info("drive page ready: %s", "   ".join(urls))
    log.info("Ctrl+C stops the robot and the page")
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            loop.stop()  # stops the base
        finally:
            robot.disconnect()
        log.info("robot stopped")


if __name__ == "__main__":
    main()
