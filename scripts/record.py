"""Record demonstrations on LeKiwi into a LeRobot dataset.

    uv run python scripts/record.py --name pick_v1 --object sock --episodes 30
    uv run python scripts/record.py --name pick_v1 --object can --episodes 30     # same dataset, more episodes

Run it again with the same --name to ADD episodes: nothing is overwritten, and a crash loses
at most the episode being recorded. The dataset is pushed to the Hub when a session ends.

Keys (terminal focused): RIGHT ARROW = end the episode, LEFT ARROW = redo it, ESC = stop the
session. Use the arrows, not the letters: r, f and q also drive the base.

    uv run python scripts/record.py --name rehearsal --object sock --episodes 2 --dry-run

--dry-run rehearses the whole session with a fake robot and leader (no hardware, nothing
uploaded): use it to learn the keys and to check the laptop before the robot is free.

Protocol and quality rules: docs/DATA_COLLECTION.md. Tonight's plan: docs/CE_SOIR.md.
Follows lerobot 0.7.0 `examples/lekiwi/record.py`.
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

from lerobot.datasets import LeRobotDataset
from lerobot.processor import make_default_processors
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.constants import ACTION, HF_LEROBOT_HOME, OBS_STR
from lerobot.utils.feature_utils import hw_to_dataset_features
from lerobot.utils.keyboard_input import init_keyboard_listener
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_visualization

from makai.config import REPO_ROOT, load_config
from makai.robot.lekiwi import make_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", required=True, help="dataset name, e.g. pick_v1")
    parser.add_argument("--object", required=True, help="what is being picked up: sock, can...")
    parser.add_argument("--episodes", type=int, default=30, help="episodes to record in this session")
    parser.add_argument("--episode-time", type=float, default=15.0, help="seconds, upper bound")
    parser.add_argument("--reset-time", type=float, default=10.0, help="seconds to reset the scene")
    parser.add_argument(
        "--task", default=None, help="task string; default: 'Pick up the <object> from the floor'"
    )
    parser.add_argument("--no-push", action="store_true", help="keep the dataset on this laptop")
    parser.add_argument(
        "--no-display", action="store_true", help="do not open Rerun (if the loop is too slow)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="fake robot and leader: rehearse without hardware"
    )
    args = parser.parse_args()

    cfg = load_config()
    fps = cfg["robot"]["fps"]
    task = args.task or f"Pick up the {args.object} from the floor"
    namespace = cfg["hub"]["namespace"]
    push = not (args.no_push or args.dry_run)
    if args.dry_run or namespace == "CHANGE_ME":
        if push:
            print(
                "hub.namespace is not set in configs/local.yaml: recording locally, nothing will be uploaded."
            )
        namespace, push = "local", False
    repo_id = f"{namespace}/makai_{args.name}"
    root = Path(HF_LEROBOT_HOME) / repo_id

    if args.dry_run:
        from makai.robot.fake import FakeKeyboard, FakeKiwi, FakeLeader

        robot = FakeKiwi(make_client(cfg).config)
        leader = FakeLeader(SO101LeaderConfig(port="none", id="fake_leader"))
        keyboard = FakeKeyboard(KeyboardTeleopConfig())
    else:
        robot = make_client(cfg)
        leader = SO101Leader(
            SO101LeaderConfig(port=cfg["teleop"]["leader_port"], id=cfg["teleop"]["leader_id"])
        )
        keyboard = KeyboardTeleop(KeyboardTeleopConfig())

    if root.exists():
        dataset = LeRobotDataset.resume(repo_id, root=root, image_writer_threads=4)
        print(f"Adding to {repo_id}: it already holds {dataset.meta.total_episodes} episodes.")
    else:
        features = {
            **hw_to_dataset_features(robot.action_features, ACTION),
            **hw_to_dataset_features(robot.observation_features, OBS_STR),
        }
        dataset = LeRobotDataset.create(
            repo_id=repo_id,
            fps=fps,
            features=features,
            root=root,
            robot_type=robot.name,
            use_videos=True,
            image_writer_threads=4,
        )
        print(f"New dataset {repo_id} in {root}")

    robot.connect()
    leader.connect()
    keyboard.connect()
    listener, events = init_keyboard_listener()
    if not args.no_display:
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
        display_data=not args.no_display,
    )

    log_path = REPO_ROOT / "outputs" / "recordings" / f"{args.name}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    recorded, sounds = 0, not args.dry_run
    started = time.time()
    try:
        while recorded < args.episodes and not events["stop_recording"]:
            log_say(f"Episode {recorded + 1} of {args.episodes}", play_sounds=sounds)
            record_loop(**loop, dataset=dataset, control_time_s=args.episode_time)

            if not events["stop_recording"] and (recorded < args.episodes - 1 or events["rerecord_episode"]):
                log_say("Reset", play_sounds=sounds)
                record_loop(**loop, control_time_s=args.reset_time)

            if events["rerecord_episode"]:
                log_say("Again", play_sounds=sounds)
                events["rerecord_episode"] = False
                events["exit_early"] = False
                dataset.clear_episode_buffer()
                continue

            dataset.save_episode()
            recorded += 1
            with log_path.open("a", newline="") as f:  # which episode holds which object
                csv.writer(f).writerow(
                    [
                        dataset.meta.total_episodes - 1,
                        args.object,
                        datetime.now().isoformat(timespec="seconds"),
                    ]
                )
    finally:
        log_say("Session finished", play_sounds=sounds)
        robot.disconnect()
        leader.disconnect()
        keyboard.disconnect()
        if listener is not None:
            listener.stop()
        dataset.finalize()
        total = dataset.meta.total_episodes
        minutes = (time.time() - started) / 60
        print(
            f"\n{recorded} episodes of '{args.object}' recorded in {minutes:.0f} min. {repo_id} now holds {total}."
        )
        print(f"Episode list: {log_path.relative_to(REPO_ROOT)}   local copy: {root}")
        if push and recorded > 0:
            try:
                dataset.push_to_hub()
                print(f"Uploaded: https://huggingface.co/datasets/{repo_id}")
            except Exception as error:  # the data is safe on disk: never lose a session to the network
                print(f"UPLOAD FAILED ({error}). The data is safe locally. Retry later with:")
                print(f"  uv run hf upload {repo_id} {root} --repo-type dataset")
        if args.dry_run:
            print("Dry run: this was a rehearsal. Delete it with:  rm -rf", root)


if __name__ == "__main__":
    main()
