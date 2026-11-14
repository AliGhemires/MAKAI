"""Teleoperate LeKiwi: leader arm for the arm, keyboard for the base.

    uv run python scripts/teleop.py

Base: w/s forward/back, a/d left/right, z/x turn, r/f speed up/down.
Press `p` to print the current arm pose and append it to configs/poses_captured.yaml
(then copy it under the right name into configs/arm_poses.yaml).

Before: the host must be running on the Pi (docs/SETUP.md).
"""

import time
from datetime import datetime

import yaml
from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.visualization_utils import init_visualization, log_visualization_data

from makai.config import CONFIG_DIR, load_config
from makai.robot.lekiwi import ARM_KEYS, make_client


def main() -> None:
    cfg = load_config()
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
        robot.disconnect()
        leader.disconnect()
        keyboard.disconnect()


if __name__ == "__main__":
    main()
