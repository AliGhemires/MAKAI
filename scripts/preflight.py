"""Check everything a recording session needs, BEFORE recording anything.

    uv run python scripts/preflight.py            # robot + leader connected, host running on the Pi
    uv run python scripts/preflight.py --dry-run  # no hardware: checks this laptop only

Nothing is commanded: the robot does not move. Fix every FAIL before the first episode;
a WARN is your call.
"""

from __future__ import annotations

import argparse
import shutil
import time

import numpy as np
import yaml
from lerobot.utils.robot_utils import precise_sleep

from makai.config import CONFIG_DIR, load_config
from makai.robot.lekiwi import ARM_KEYS, make_client

results: list[tuple[str, str, str]] = []


def report(level: str, name: str, detail: str = "") -> None:
    results.append((level, name, detail))
    print(f"[{level:4s}] {name}" + (f": {detail}" if detail else ""))


def check(ok: bool, name: str, detail: str = "", level: str = "FAIL") -> bool:
    report("ok" if ok else level, name, detail)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="fake robot and leader: check this laptop only"
    )
    args = parser.parse_args()
    cfg = load_config()
    fps = cfg["robot"]["fps"]

    # --- this laptop
    free_gb = shutil.disk_usage(CONFIG_DIR).free / 1e9
    check(free_gb > 5, "disk space", f"{free_gb:.0f} GB free (a 60-episode session needs about 1 GB)")
    check(cfg["hub"]["namespace"] != "CHANGE_ME", "hub.namespace set in configs/local.yaml",
          cfg["hub"]["namespace"], level="WARN")  # fmt: skip
    poses = yaml.safe_load((CONFIG_DIR / cfg["manipulation"]["poses_file"]).read_text())
    home_set = any(abs(v) > 1e-6 for v in poses["home"].values())
    check(
        home_set,
        "home pose captured in configs/arm_poses.yaml",
        "still the placeholder zeros" if not home_set else "",
        level="WARN",
    )

    # --- robot and leader
    if args.dry_run:
        from lerobot.teleoperators.so_leader import SO101LeaderConfig

        from makai.robot.fake import FakeKiwi, FakeLeader

        robot = FakeKiwi(make_client(cfg).config)
        leader = FakeLeader(SO101LeaderConfig(port="none", id="fake_leader"))
    else:
        from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig

        robot = make_client(cfg)
        leader = SO101Leader(
            SO101LeaderConfig(port=cfg["teleop"]["leader_port"], id=cfg["teleop"]["leader_id"])
        )

    try:
        robot.connect()
        report("ok", "robot reachable", f"{cfg['robot']['remote_ip']} (host running on the Pi)")
    except Exception as error:
        report("FAIL", "robot reachable", f"{error}. Is the host running? Same network? Right IP?")
        robot = None
    try:
        leader.connect()
        report("ok", "leader arm connected", str(cfg["teleop"]["leader_port"]))
    except Exception as error:
        report("FAIL", "leader arm connected", f"{error}. Port in configs/local.yaml? `lerobot-find-port`")
        leader = None

    if robot is not None:
        time.sleep(0.5)
        first = robot.get_observation()
        missing = [key for key in ARM_KEYS if key not in first]
        check(not missing, "arm state received", f"missing {missing}" if missing else "6 joints")
        for name, cam in cfg["robot"]["cameras"].items():
            image = first.get(name)
            expected = (cam["height"], cam["width"], 3)
            if not check(image is not None and tuple(image.shape) == expected, f"camera '{name}' image",
                         f"expected {expected}, got {None if image is None else tuple(image.shape)}"):  # fmt: skip
                continue
            check(
                float(np.mean(image)) > 8,
                f"camera '{name}' not black",
                f"mean brightness {np.mean(image):.0f}",
            )
            time.sleep(0.4)
            later = robot.get_observation().get(name)
            frozen = later is None or float(np.abs(later.astype(int) - image.astype(int)).mean()) < 0.05
            check(not frozen, f"camera '{name}' is live", "identical frames 0.4 s apart: wave a hand in front of it" if frozen else "",
                  level="WARN")  # fmt: skip

        # What the recording loop does on every tick, minus sending commands: how long does it
        # take, and do we really get a new camera image each time?
        ticks, work = 90, []
        cameras = list(cfg["robot"]["cameras"])
        fresh, previous = dict.fromkeys(cameras, 0), dict.fromkeys(cameras)
        began = time.perf_counter()
        for _ in range(ticks):
            tick = time.perf_counter()
            observation = robot.get_observation()
            if leader is not None:
                leader.get_action()
            work.append(time.perf_counter() - tick)
            for name in cameras:
                image = observation.get(name)
                signature = None if image is None else hash(image[::4, ::4].tobytes())
                fresh[name] += signature != previous[name]
                previous[name] = signature
            precise_sleep(max(0.0, 1.0 / fps - work[-1]))
        seconds = time.perf_counter() - began
        budget_ms, mean_ms, worst_ms = 1000 / fps, 1000 * float(np.mean(work)), 1000 * max(work)
        check(mean_ms < 0.7 * budget_ms, "time per tick",
              f"mean {mean_ms:.0f} ms, worst {worst_ms:.0f} ms, for a budget of {budget_ms:.0f} ms")  # fmt: skip
        # How many NEW images per second each camera really delivers. A camera in the dark often
        # drops to 10-15 a second (long exposure): the picture is jerky and blurred.
        for name in cameras:
            rate = fresh[name] / seconds
            check(rate >= 0.8 * fps, f"camera '{name}' frame rate", f"{rate:.0f} new images per second for {fps} asked"
                  + ("" if rate >= 0.8 * fps else ": too dark for it (add light, or fix its exposure), or a weak USB cable"),
                  level="WARN")  # fmt: skip

    if leader is not None:
        joints = leader.get_action()
        check(
            len(joints) == 6,
            "leader arm readable",
            ", ".join(f"{k.removesuffix('.pos')} {v:.0f}" for k, v in joints.items()),
        )
        leader.disconnect()
    if robot is not None:
        robot.disconnect()

    fails = sum(level == "FAIL" for level, _, _ in results)
    warns = sum(level == "WARN" for level, _, _ in results)
    print(f"\n{'READY TO RECORD' if not fails else 'NOT READY'}: {fails} FAIL, {warns} WARN")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
