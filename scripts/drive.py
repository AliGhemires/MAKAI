"""The robot's console: run the sweeping mission and watch its map, drive the base, see the
cameras and the arm, measure moves, look at the training results.
Open it on a phone, a tablet or a laptop of the same network.

On the Pi, without the host (motor board and cameras on the Pi), in the `lerobot` conda env:

    cd ~/MAKAI && python scripts/drive.py --link wired

then open http://lekiwi.local:8000 (or http://<Pi IP>:8000). Start it inside `tmux`: closing
the SSH session stops the robot and the page otherwise. The cameras of `robot.cameras` are
opened directly; the arm is read (never moved) if it was calibrated on the Pi.

Through the host (host running on the Pi), from a laptop: cameras and arm come with the
host's observations. Not at the same time as teleop.py or record.py (they share the stream).

    uv run python scripts/drive.py --link host        # then http://localhost:8000

This is where the mission runs (the policies need the laptop): the page is then the console,
with the Mission, Drive, Cameras and Data tabs; the driving page alone stays at /drive.

Without a robot, to try the console and watch a simulated mission:

    uv run python scripts/drive.py --sim
    uv run python scripts/drive.py --sim --sim-scale 0.96   # a robot whose wheels are 4 % off

Precise moves and their tape measurements are saved in data/move_trials.csv (not in git).
"""

from __future__ import annotations

import argparse
import logging
import signal
import socket
import subprocess
import sys
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


def lan_addresses() -> list[str]:
    """This machine's IPv4 addresses. On the Pi, `hostname -I` lists them all, including the
    access point's 10.42.0.1, which has no route out (the trick below needs one)."""
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2).stdout
            found = [a for a in out.split() if a.count(".") == 3 and not a.startswith("127.")]
            if found:
                return found
        except (OSError, subprocess.SubprocessError):
            pass
    try:  # no packet is sent: this only picks the interface of the default route
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return [sock.getsockname()[0]]
    except OSError:
        return []


def make_sim(scale: float):
    """Simulated base that really moves `scale` times what its wheels report (a wrong wheel
    radius, or slip). Returns the robot and where it really is, the "tape" of the simulation.
    It also fakes an arm moving slowly, a battery and motor measurements, to try the page."""
    import math

    from makai.contracts import BaseVelocity, Observation
    from makai.robot.lekiwi import ARM_KEYS
    from makai.sim.world import SimRobot, sweep_world

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

        def motor_details(self) -> dict[str, dict]:
            names = ["base_left_wheel", "base_back_wheel", "base_right_wheel"] + [
                k.removesuffix(".pos") for k in ARM_KEYS
            ]
            t = self.world.time
            return {
                name: {
                    "id": [7, 8, 9, 1, 2, 3, 4, 5, 6][i],
                    "position": int(2048 + 600 * math.sin(0.3 * t + i)) % 4096,
                    "velocity": int(self._vel.x * 4000) if i < 3 else 0,
                    "load_pct": round(12 * math.sin(0.7 * t + i), 1),
                    "current_ma": round(abs(80 * math.sin(0.7 * t + i))),
                    "voltage_v": 12.3,
                    "temperature_c": 34 if i < 3 else 38,
                    "torque": i < 3,
                    "moving": i < 3 and self._vel.x != 0,
                    "errors": [],
                }
                for i, name in enumerate(names)
            }

    robot = MiscalibratedSim(sweep_world(), dt=1 / SIM_HZ)  # a room with a bin, a basket and things to pick
    return robot, lambda: (robot.world.x, robot.world.y, robot.world.yaw)


def sim_things(world) -> list:
    """What the simulated cameras draw on the floor: the objects, and the two stations."""
    colours = {"clothing": (214, 120, 42), "trash": (52, 104, 235)}  # BGR, as on the map
    things = [(o.x, o.y, colours.get(o.category.value, (200, 200, 200)), 0.05) for o in world.objects]
    return things + [(sx, sy, (230, 230, 230), 0.14) for sx, sy in world.stations.values()]


def plan_of(sweep, traced: bool = False) -> dict:
    """The room, the route of the sweep and the stations, for the map of the console."""
    from makai.orchestrator.sweep import sweep_waypoints

    return {
        "pattern": sweep.pattern,
        "traced": traced,  # the zone was traced by driving the robot around it
        "room": {
            "length_m": sweep.room.length_m,
            "width_m": sweep.room.width_m,
            "margin_m": sweep.room.margin_m,
            "y_offset_m": sweep.room.y_offset_m,
        },
        "waypoints": sweep_waypoints(sweep),
        "stations": {
            key.value: {"x": s.x, "y": s.y, "dock_x": s.dock_x, "dock_y": s.dock_y}
            for key, s in sweep.stations.items()
        },
    }


def sim_runner(loop, driver, robot, cfg):
    """The sweeping mission on the simulated robot of the page: same code as on the real one."""
    from dataclasses import replace

    from makai.app import mission_config
    from makai.contracts import Category
    from makai.navigation.coverage import Room
    from makai.orchestrator.sweep import Station, SweepConfig, SweepMission
    from makai.robot.autopilot import MissionRunner
    from makai.sim.world import SimDrop, SimPerception, SimPick, sweep_world

    world = robot.world
    mission_cfg = mission_config(cfg)
    stations = {Category.TRASH: Station(-0.35, 0.0), Category.CLOTHING: Station(-0.35, 0.7, 0.0, 0.7)}
    whole = SweepConfig(room=Room(length_m=2.4, width_m=1.8), stations=stations)
    plan = {"sweep": whole, "traced": False}
    goal = (mission_cfg.approach.goal_x_m, mission_cfg.approach.goal_y_m)

    def build(tap):
        # A mission always starts in front of the bin, facing the room: put the simulated robot there.
        world.x, world.y, world.yaw = 0.0, 0.0, 0.0
        return SweepMission(
            tap,
            SimPerception(world, station_max_range_m=1.2, max_range_m=1.5),
            SimPick(world, goal_xy=goal, success_rate=0.85, duration_s=2.5, seed=runner.runs),
            SimDrop(world, duration_s=1.5),
            mission_cfg,
            plan["sweep"],
        )

    def reset() -> None:
        fresh = sweep_world()
        world.objects[:] = fresh.objects
        world.delivered.clear()
        world.carrying, world.x, world.y, world.yaw = None, 0.0, 0.0, 0.0
        loop.reset_odometry()

    def use_zone(room) -> None:  # in simulation the traced zone is not written to configs/
        plan["sweep"] = replace(whole, room=Room(**room)) if room else whole
        plan["traced"] = room is not None

    runner = MissionRunner(
        loop, driver, build, lambda: plan_of(plan["sweep"], plan["traced"]), reset, True, use_zone
    )
    return runner


def real_runner(loop, driver, cfg):
    """The sweeping mission on the real robot, through the host. The detector and the policies
    are loaded at the first start and kept."""
    from makai.app import mission_config, sweep_config
    from makai.navigation.zone import forget_zone, load_zone, save_zone
    from makai.robot.autopilot import MissionRunner

    plan, parts = {"sweep": sweep_config(cfg)}, {}

    def use_zone(room) -> None:  # kept in configs/zone.yaml: it survives a restart of the page
        if room is None:
            forget_zone()
        else:
            save_zone(room)
        plan["sweep"] = sweep_config(cfg)

    def build(tap):
        from makai.manipulation.skills import build_drop_skill, build_pick_skill
        from makai.orchestrator.sweep import SweepMission
        from makai.perception.pipeline import build_perception

        if not parts:
            parts.update(
                perception=build_perception(cfg), pick=build_pick_skill(cfg), drop=build_drop_skill(cfg)
            )
        return SweepMission(
            tap, parts["perception"], parts["pick"], parts["drop"], mission_config(cfg), plan["sweep"]
        )

    return MissionRunner(
        loop, driver, build, lambda: plan_of(plan["sweep"], load_zone() is not None), use_zone=use_zone
    )


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
        captures = [
            SimCamera(cameras, name, truth, args.camera_fps, things=lambda: sim_things(robot.world))
            for name in ("front", "wrist")
        ]
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
    runner = None  # in wired mode (on the Pi) there is no mission: the policies need the laptop
    if args.sim:
        runner = sim_runner(loop, driver, robot, cfg)
    elif link == "host":
        runner = real_runner(loop, driver, cfg)
    info["mission"] = runner is not None
    http_port = args.http_port or int(drive_cfg.get("http_port", 8000))
    try:  # before touching the robot: a busy port should not leave the wheels armed
        server = DriveServer((args.bind, http_port), loop, driver, info, cameras, runner)
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
        source = getattr(robot.client, "calibration_file", None)
        log.info(
            "arm: %s",
            f"read from the bus, calibration {source}" if arm else "not read (no calibration, or no arm)",
        )
    urls = [f"http://localhost:{http_port}"]
    if args.bind != "127.0.0.1":
        urls += [f"http://{address}:{http_port}" for address in lan_addresses()]
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
