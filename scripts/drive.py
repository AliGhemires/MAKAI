"""The robot's control page: drive the base, see the cameras and the arm, measure moves.
Open it on a phone, a tablet or a laptop of the same network.

On the Pi, without the host (motor board and cameras on the Pi), in the `lerobot` conda env:

    cd ~/MAKAI && python scripts/drive.py --link wired

then open http://lekiwi.local:8000 (or http://<Pi IP>:8000). Start it inside `tmux`: closing
the SSH session stops the robot and the page otherwise. The cameras of `robot.cameras` are
opened directly; the arm is read (never moved) if it was calibrated on the Pi.

Through the host (host running on the Pi), from a laptop: cameras and arm come with the
host's observations. Not at the same time as teleop.py or record.py (they share the stream).

    uv run python scripts/drive.py --link host        # then http://localhost:8000

Without a robot, to try the page:

    uv run python scripts/drive.py --sim
    uv run python scripts/drive.py --sim --sim-scale 0.96   # a robot whose wheels are 4 % off

Precise moves and their tape measurements are saved in data/move_trials.csv (not in git).
"""

from __future__ import annotations

import argparse
import logging
import signal
import socket
from dataclasses import asdict

from makai.config import REPO_ROOT, load_config
from makai.robot.cameras import CameraCapture, CameraHub, SimCamera
from makai.robot.drive_server import DriveServer
from makai.robot.lekiwi import LINKS, BaseGeometry, LeKiwiRobot
from makai.robot.manual import DriveLimits, DriveLoop, ManualDriver
from makai.robot.moves import TrialLog

TELEMETRY_HZ = 10.0
SIM_HZ = 50.0  # the simulated robot gives no encoders: read its speed at the control rate
log = logging.getLogger("drive")


def lan_address() -> str | None:
    """This machine's address on the network (no packet is sent: it only picks the interface)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
    except OSError:
        return None


def make_sim(scale: float):
    """Simulated base that really moves `scale` times what its wheels report (a wrong wheel
    radius, or slip). Returns the robot and where it really is, the "tape" of the simulation.
    It also fakes an arm moving slowly, a battery and motor temperatures, to try the page."""
    import math

    from makai.contracts import BaseVelocity, Observation
    from makai.robot.lekiwi import ARM_KEYS
    from makai.sim.world import SimRobot, SimWorld

    class MiscalibratedSim(SimRobot):
        def get_observation(self) -> Observation:
            v = self._vel
            self.world.advance(BaseVelocity(v.x * scale, v.y * scale, v.theta * scale), self.dt)
            t = self.world.time
            arm = {key: 40 * math.sin(0.3 * t + i) for i, key in enumerate(ARM_KEYS[:-1])}
            arm[ARM_KEYS[-1]] = 50 + 45 * math.sin(0.5 * t)  # gripper, 0 to 100
            return Observation(stamp=t, base_velocity=v, arm=arm)

        def battery_voltage(self) -> float:
            return 12.3

        def motor_temperatures(self) -> dict[str, int]:
            names = ["base_left_wheel", "base_back_wheel", "base_right_wheel"]
            return {**dict.fromkeys(names, 34), **{key.removesuffix(".pos"): 38 for key in ARM_KEYS}}

    robot = MiscalibratedSim(SimWorld(), dt=1 / SIM_HZ)
    return robot, lambda: (robot.world.x, robot.world.y, robot.world.yaw)


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
    parser.add_argument(
        "--sim-scale", type=float, default=1.0, help="simulated robot moves this times what its wheels say"
    )
    parser.add_argument("--serial-port", help="motor board port in wired mode (default: robot.base.port)")
    parser.add_argument("--http-port", type=int, help="port of the page (default: teleop.drive.http_port)")
    parser.add_argument("--bind", default="0.0.0.0", help="listen address; 127.0.0.1 = this machine only")
    parser.add_argument("--no-cameras", action="store_true", help="do not open the cameras (wired mode)")
    parser.add_argument("--camera-fps", type=float, default=10.0, help="images per second sent to the page")
    parser.add_argument("--camera-quality", type=int, default=70, help="JPEG quality, 30 to 95")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    cfg = load_config()
    drive_cfg = cfg["teleop"]["drive"]
    limits = DriveLimits.from_config(drive_cfg)
    geometry = BaseGeometry.from_config(cfg["robot"]["base"])
    truth = None
    if args.sim:
        (robot, truth), link, serial_port = make_sim(args.sim_scale), "sim", None
    else:
        link = args.link or cfg["robot"].get("link", "host")
        if args.serial_port:
            cfg["robot"]["base"]["port"] = args.serial_port
        serial_port = cfg["robot"]["base"]["port"] if link == "wired" else None
        robot = LeKiwiRobot.from_config(cfg, link=link)

    cameras = CameraHub(quality=max(30, min(95, args.camera_quality)))
    captures: list = []
    camera_cfg = cfg["robot"].get("cameras", {})
    if args.sim:
        captures = [SimCamera(cameras, name, truth, args.camera_fps) for name in ("front", "wrist")]
    elif link == "wired" and not args.no_cameras:
        captures = [
            CameraCapture(
                cameras,
                name,
                cam["index_or_path"],
                cam["width"],
                cam["height"],
                cam.get("fps", 15),
                args.camera_fps,
            )
            for name, cam in camera_cfg.items()
        ]
    elif link == "host":
        for name, cam in camera_cfg.items():
            cameras.expect(name, f"host: {cam['index_or_path']}")

    driver = ManualDriver(limits)
    trials = TrialLog(REPO_ROOT / "data" / ("move_trials_sim.csv" if args.sim else "move_trials.csv"))
    loop = DriveLoop(
        robot,
        driver,
        geometry,
        telemetry_hz=SIM_HZ if args.sim else TELEMETRY_HZ,
        trials=trials,
        truth=truth,
        cameras=cameras,
    )
    info = {
        "link": link,
        "serial_port": serial_port,
        "limits": asdict(limits),
        "wheels": [name.removeprefix("base_").removesuffix("_wheel") for name in geometry.names],
        "cameras": cameras.names,
        "camera_fps": args.camera_fps,
    }
    http_port = args.http_port or int(drive_cfg.get("http_port", 8000))
    try:  # before touching the robot: a busy port should not leave the wheels armed
        server = DriveServer((args.bind, http_port), loop, driver, info, cameras)
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
    for capture in captures:
        capture.start()
    arm = getattr(robot.client, "arm", None) if hasattr(robot, "client") else None
    if link == "wired":
        log.info(
            "arm: %s",
            "read from the bus" if arm else "not read (no calibration file on this machine, or no arm)",
        )
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
        for capture in captures:
            capture.stop()
        try:
            loop.stop()  # stops the base
        finally:
            robot.disconnect()
        log.info("robot stopped")


if __name__ == "__main__":
    main()
