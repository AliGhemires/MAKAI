"""Record demonstrations on LeKiwi into a LeRobot dataset (pushed to the Hub at the end).

    uv run python scripts/record.py --name pick_sock_v1 --episodes 25 --task "Pick up the object from the floor"

Keys while recording (terminal focused): right arrow / n = end episode, left arrow / r = redo
it, ESC / q = stop and upload. Follows lerobot 0.7.0 `examples/lekiwi/record.py`.
Protocol and quality rules: docs/DATA_COLLECTION.md. Read them before recording anything.
"""

import argparse

from lerobot.datasets import LeRobotDataset
from lerobot.processor import make_default_processors
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.constants import ACTION, OBS_STR
from lerobot.utils.feature_utils import hw_to_dataset_features
from lerobot.utils.keyboard_input import init_keyboard_listener
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_visualization

from makai.config import load_config
from makai.robot.lekiwi import make_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--name",
        required=True,
        help="dataset name, e.g. pick_sock_v1 (the Hub namespace comes from the config)",
    )
    parser.add_argument("--task", default=None, help="task string; defaults to manipulation.pick.task")
    parser.add_argument("--episodes", type=int, default=25)
    parser.add_argument(
        "--episode-time", type=float, default=15.0, help="seconds, upper bound (end early with ->)"
    )
    parser.add_argument("--reset-time", type=float, default=10.0, help="seconds to reset the scene")
    parser.add_argument("--no-push", action="store_true", help="keep the dataset local")
    args = parser.parse_args()

    cfg = load_config()
    fps = cfg["robot"]["fps"]
    task = args.task or cfg["manipulation"]["pick"]["task"]
    repo_id = f"{cfg['hub']['namespace']}/makai_{args.name}"

    robot = make_client(cfg)
    leader = SO101Leader(SO101LeaderConfig(port=cfg["teleop"]["leader_port"], id=cfg["teleop"]["leader_id"]))
    keyboard = KeyboardTeleop(KeyboardTeleopConfig())

    features = {
        **hw_to_dataset_features(robot.action_features, ACTION),
        **hw_to_dataset_features(robot.observation_features, OBS_STR),
    }
    dataset = LeRobotDataset.create(
        repo_id=repo_id,
        fps=fps,
        features=features,
        robot_type=robot.name,
        use_videos=True,
        image_writer_threads=4,
    )

    robot.connect()
    leader.connect()
    keyboard.connect()
    listener, events = init_keyboard_listener()
    init_visualization("rerun", session_name="makai_record")
    teleop_action_processor, robot_action_processor, robot_observation_processor = make_default_processors()
    loop = dict(
        robot=robot,
        events=events,
        fps=fps,
        teleop_action_processor=teleop_action_processor,
        robot_action_processor=robot_action_processor,
        robot_observation_processor=robot_observation_processor,
        teleop=[leader, keyboard],
        single_task=task,
        display_data=True,
    )

    recorded = 0
    try:
        while recorded < args.episodes and not events["stop_recording"]:
            log_say(f"Recording episode {recorded + 1} of {args.episodes}")
            record_loop(**loop, dataset=dataset, control_time_s=args.episode_time)

            if not events["stop_recording"] and (recorded < args.episodes - 1 or events["rerecord_episode"]):
                log_say("Reset the scene")
                record_loop(**loop, control_time_s=args.reset_time)

            if events["rerecord_episode"]:
                log_say("Re-recording episode")
                events["rerecord_episode"] = False
                events["exit_early"] = False
                dataset.clear_episode_buffer()
                continue

            dataset.save_episode()
            recorded += 1
    finally:
        log_say("Stop recording")
        robot.disconnect()
        leader.disconnect()
        keyboard.disconnect()
        if listener is not None:
            listener.stop()
        dataset.finalize()
        if not args.no_push and recorded > 0:
            dataset.push_to_hub()
        print(f"{recorded} episodes saved in {repo_id}")


if __name__ == "__main__":
    main()
