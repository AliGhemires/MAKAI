"""Teleoperate LeKiwi: leader arm for the arm, keyboard for the base.

    uv run python scripts/teleop.py

Base: w/s forward/back, a/d left/right, z/x turn, r/f speed up/down.
Press `p` to print the current arm pose and append it to configs/poses_captured.yaml
(then copy it under the right name into configs/arm_poses.yaml).

    uv run python scripts/teleop.py --save-front data/robot_frames/sock

also saves 3 front-camera images per second: drive around ONE object for 30 s, repeat for each
object and for the empty floor, then retrain the detector on the robot's own camera
(scripts/train_detector.py).

Before: the host must be running on the Pi (docs/SETUP.md).
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

import cv2
import yaml
from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.visualization_utils import init_visualization, log_visualization_data

from makai.config import CONFIG_DIR, load_config
from makai.robot.lekiwi import ARM_KEYS, make_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--save-front", metavar="DIR", help="save 3 front-camera images per second into DIR")
    args = parser.parse_args()
    cfg = load_config()
    frames_dir = Path(args.save_front) if args.save_front else None
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)
    tick = saved = 0
    fps = cfg["robot"]["fps"]
    robot = make_client(cfg)
    leader = SO101Leader(SO101LeaderConfig(port=cfg["teleop"]["leader_port"], id=cfg["teleop"]["leader_id"]))
    keyboard = KeyboardTeleop(KeyboardTeleopConfig(id="keyboard"))
    robot.connect()
    leader.connect()
    keyboard.connect()
    init_visualization("rerun", session_name="makai_teleop")

    p_was_down = False
    print("Teleop running. Ctrl-C to stop.")
    try:
        while True:
            t0 = time.perf_counter()
            observation = robot.get_observation()
            arm_action = {f"arm_{k}": v for k, v in leader.get_action().items()}
            keys = keyboard.get_action()
            action = {**arm_action, **robot._from_keyboard_to_base_action(keys)}
            robot.send_action(action)
            log_visualization_data("rerun", observation=observation, action=action)

            tick += 1
            if (
                frames_dir is not None
                and tick % max(1, fps // 3) == 0
                and observation.get("front") is not None
            ):
                name = frames_dir / f"f_{datetime.now():%H%M%S}_{tick:06d}.jpg"
                cv2.imwrite(str(name), cv2.cvtColor(observation["front"], cv2.COLOR_RGB2BGR))
                saved += 1

            p_down = "p" in keys
            if p_down and not p_was_down:
                pose = {k: round(float(observation[k]), 1) for k in ARM_KEYS if k in observation}
                name = f"pose_{datetime.now():%H%M%S}"
                with open(CONFIG_DIR / "poses_captured.yaml", "a") as f:
                    f.write(yaml.safe_dump({name: pose}, default_flow_style=True, width=1000))
                print(f"saved {name}: {pose}")
            p_was_down = p_down
            precise_sleep(max(1.0 / fps - (time.perf_counter() - t0), 0.0))
    except KeyboardInterrupt:
        pass
    finally:
        if frames_dir is not None:
            print(f"{saved} front-camera images saved in {frames_dir}")
        robot.disconnect()
        leader.disconnect()
        keyboard.disconnect()


if __name__ == "__main__":
    main()
