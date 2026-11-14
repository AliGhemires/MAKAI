"""Record demonstrations on LeKiwi into a LeRobot dataset.

    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30
    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30     # adds 30 more

Run it again with the same --name to ADD episodes: nothing is overwritten, and a crash loses
at most the episode being recorded. The dataset is pushed to the Hub when a session ends.

Hands-free by default: no key to press, both hands stay on the job.
  1. put the leader on its rest (the home pose) and press Enter once: that pose is "home";
  2. "Ready" is spoken when the arm is back home and still: place the object;
  3. recording starts by itself when you move the leader, and the episode is saved by itself
     once the arm is back home and has stayed still for one second. Its number is spoken.
Every episode therefore starts from the same pose, has no dead time at the start, and ends
with the same second of stillness. An episode that never comes back home is dropped.
  LEFT ARROW  while recording: drop this episode. Just after one was saved: mark it as bad.
  RIGHT ARROW while recording: save now.        ESC: stop the session.
If "Ready" never comes, the arm does not settle within the tolerance: raise --home-tol, or
use --manual (RIGHT ARROW ends each episode, LEFT ARROW redoes it, fixed reset time).
Use the arrows, not the letters: r, f and q also drive the base.

    uv run python scripts/record.py --name rehearsal --object sock --episodes 2 --dry-run

--dry-run rehearses the whole session with a fake robot and leader (no hardware, nothing
uploaded): use it to check the laptop before the robot is free.

Protocol and quality rules: docs/DATA_COLLECTION.md. Tonight's plan: docs/CE_SOIR.md.
The --manual loop follows lerobot 0.7.0 `examples/lekiwi/record.py`.
"""

import argparse
import csv
import os
import shutil
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from lerobot.datasets import LeRobotDataset
from lerobot.processor import make_default_processors
from lerobot.scripts.lerobot_record import record_loop
from lerobot.teleoperators.keyboard import KeyboardTeleop, KeyboardTeleopConfig
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.constants import ACTION, HF_LEROBOT_HOME, OBS_STR
from lerobot.utils.feature_utils import build_dataset_frame, hw_to_dataset_features
from lerobot.utils.keyboard_input import init_keyboard_listener
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_visualization, log_visualization_data

from makai.config import REPO_ROOT, load_config
from makai.robot.lekiwi import ARM_KEYS, make_client

STOP = {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
# The gripper is left out of "is the arm home?": it is open at the start and closed at the end.
ARM = [key for key in ARM_KEYS if "gripper" not in key]


def hands_free_session(robot, leader, dataset, events, args, fps, task, display, say, on_saved, on_bad):
    """Record episodes that start and end by themselves (see the module docstring)."""

    def tick():
        observation = robot.get_observation()
        leader_action = leader.get_action()
        action = {**{f"arm_{key}": value for key, value in leader_action.items()}, **STOP}
        robot.send_action(action)
        arm = np.array([float(observation[key]) for key in ARM])
        hand = np.array([float(leader_action[key.removeprefix("arm_")]) for key in ARM])
        return observation, action, arm, hand

    if not args.dry_run:
        input("Put the leader on its rest, in the home pose, hands off. Then press Enter... ")
    samples = []
    for _ in range(fps):  # one second: let the arm reach the leader, then average the second half
        start = time.perf_counter()
        samples.append(tick()[2:])
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))
    home_arm = np.mean([arm for arm, _ in samples[fps // 2 :]], axis=0)
    home_hand = np.mean([hand for _, hand in samples[fps // 2 :]], axis=0)
    names = [key.removeprefix("arm_").removesuffix(".pos") for key in ARM]
    print("Home pose:", ", ".join(f"{name} {value:.0f}" for name, value in zip(names, home_arm, strict=True)))

    recent: deque = deque(maxlen=2 * fps)  # the last two seconds of arm positions
    preroll: deque = deque(maxlen=fps // 4)  # frames from just before the leader moved

    def still_for(seconds: float) -> bool:
        count = int(seconds * fps)
        if len(recent) < count:
            return False
        window = np.array(list(recent)[-count:])
        return float((window.max(axis=0) - window.min(axis=0)).max()) < args.still_tol

    state, recorded, started, saved_at = "reset", 0, 0.0, -1e9
    while recorded < args.episodes and not events["stop_recording"]:
        start = time.perf_counter()
        observation, action, arm, hand = tick()
        recent.append(arm)
        at_home = float(np.abs(arm - home_arm).max()) < args.home_tol
        frame = {
            **build_dataset_frame(dataset.features, observation, prefix=OBS_STR),
            **build_dataset_frame(dataset.features, action, prefix=ACTION),
            "task": task,
        }

        if state != "recording" and events["rerecord_episode"]:
            events["rerecord_episode"] = False
            if recorded > 0 and start - saved_at < 20.0:
                on_bad()
                say("Marked as bad")
                saved_at = -1e9

        if state == "reset":
            if at_home and still_for(0.5):
                state = "armed"
                preroll.clear()
                say("Ready")
        elif state == "armed":
            preroll.append(frame)
            if float(np.abs(hand - home_hand).max()) > args.leave_tol:
                state, started = "recording", start
                for earlier in preroll:  # ends with the current frame
                    dataset.add_frame(earlier)
        else:
            dataset.add_frame(frame)
            elapsed = start - started
            back_home = at_home and still_for(args.end_still)
            dropped = events["rerecord_episode"]
            if dropped or (back_home and elapsed < args.min_episode) or elapsed > args.episode_time:
                say("Dropped" if dropped else "Too long" if elapsed > args.episode_time else "False start")
                events["rerecord_episode"] = False
                dataset.clear_episode_buffer()
                state = "reset"
            elif back_home or events["exit_early"]:
                events["exit_early"] = False
                dataset.save_episode()
                recorded += 1
                saved_at = time.perf_counter()
                on_saved(elapsed)
                say(f"{recorded}")
                recent.clear()
                state = "reset"

        if display:
            log_visualization_data("rerun", observation=observation, action=action)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))


def manual_session(loop, dataset, events, args, say, on_saved):
    """LeRobot's own loop: the RIGHT ARROW ends each episode, then a fixed reset time."""
    recorded = 0
    while recorded < args.episodes and not events["stop_recording"]:
        say(f"Episode {recorded + 1} of {args.episodes}")
        record_loop(**loop, dataset=dataset, control_time_s=args.episode_time)

        if not events["stop_recording"] and (recorded < args.episodes - 1 or events["rerecord_episode"]):
            say("Reset")
            record_loop(**loop, control_time_s=args.reset_time)

        if events["rerecord_episode"]:
            say("Again")
            events["rerecord_episode"] = False
            events["exit_early"] = False
            dataset.clear_episode_buffer()
            continue

        dataset.save_episode()
        recorded += 1
        on_saved(None)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", required=True, help="dataset name, e.g. pick_sock_v1")
    parser.add_argument("--object", required=True, help="what is being picked up: sock, can...")
    parser.add_argument("--episodes", type=int, default=30, help="episodes to record in this session")
    parser.add_argument("--episode-time", type=float, default=15.0, help="seconds: longer is dropped")
    parser.add_argument("--task", default=None, help="default: 'Pick up the <object> from the floor'")
    parser.add_argument("--no-push", action="store_true", help="keep the dataset on this laptop")
    parser.add_argument("--no-display", action="store_true", help="do not open Rerun (if the loop is slow)")
    parser.add_argument("--dry-run", action="store_true", help="fake robot and leader: no hardware")
    parser.add_argument("--manual", action="store_true", help="end each episode with the RIGHT ARROW")
    parser.add_argument("--reset-time", type=float, default=10.0, help="--manual: seconds to reset the scene")
    parser.add_argument(
        "--home-tol", type=float, default=6.0, help="degrees from home that still count as home"
    )
    parser.add_argument(
        "--leave-tol", type=float, default=5.0, help="degrees of leader motion that start an episode"
    )
    parser.add_argument(
        "--still-tol", type=float, default=1.5, help="degrees the arm may move and still be 'still'"
    )
    parser.add_argument(
        "--end-still", type=float, default=1.0, help="seconds still at home that end an episode"
    )
    parser.add_argument("--min-episode", type=float, default=3.0, help="seconds: shorter is a false start")
    args = parser.parse_args()

    # A Mac left alone goes to sleep after a few minutes, which freezes the session (seen on
    # 14 Nov): keep it awake for as long as this script runs.
    if shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-dims", "-w", str(os.getpid())])

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
    # Every camera of the config must really arrive from the robot: a dataset recorded with one
    # camera missing cannot be completed afterwards.
    time.sleep(0.5)
    received = robot.get_observation()
    missing = [name for name in cfg["robot"]["cameras"] if received.get(name) is None]
    if missing:
        robot.disconnect()
        raise SystemExit(
            f"The robot does not send the camera(s) {missing}. Start the host on the Pi with every camera "
            "listed in robot.cameras (docs/SETUP.md, section 4), and run scripts/preflight.py."
        )
    leader.connect()
    keyboard.connect()
    listener, events = init_keyboard_listener()
    display = not args.no_display
    if display:
        init_visualization("rerun", session_name="makai_record")

    log_path = REPO_ROOT / "outputs" / "recordings" / f"{args.name}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    first_episode = dataset.meta.total_episodes
    bad: list[int] = []
    started = time.time()

    def say(text: str) -> None:
        log_say(text, play_sounds=not args.dry_run)

    def log_episode(note: str) -> None:  # which episode holds which object
        with log_path.open("a", newline="") as f:
            row = [
                dataset.meta.total_episodes - 1,
                args.object,
                datetime.now().isoformat(timespec="seconds"),
                note,
            ]
            csv.writer(f).writerow(row)

    def on_saved(seconds: float | None) -> None:
        log_episode("" if seconds is None else f"{seconds:.1f}s")

    def on_bad() -> None:
        bad.append(dataset.meta.total_episodes - 1)
        log_episode("BAD")

    try:
        if args.manual:
            processors = make_default_processors()
            loop = dict(
                robot=robot,
                events=events,
                fps=fps,
                teleop_action_processor=processors[0],
                robot_action_processor=processors[1],
                robot_observation_processor=processors[2],
                teleop=[leader, keyboard],
                single_task=task,
                display_data=display,
            )
            manual_session(loop, dataset, events, args, say, on_saved)
        else:
            hands_free_session(
                robot, leader, dataset, events, args, fps, task, display, say, on_saved, on_bad
            )
    finally:
        say("Session finished")
        robot.disconnect()
        leader.disconnect()
        keyboard.disconnect()
        if listener is not None:
            listener.stop()
        dataset.finalize()
        total = dataset.meta.total_episodes
        recorded = total - first_episode
        minutes = (time.time() - started) / 60
        print(
            f"\n{recorded} episodes of '{args.object}' recorded in {minutes:.0f} min. {repo_id} now holds {total}."
        )
        print(f"Episode list: {log_path.relative_to(REPO_ROOT)}   local copy: {root}")
        if bad:
            print(f"Marked as bad: episodes {bad}. Remove them before training with:")
            print(
                f"  uv run lerobot-edit-dataset --repo_id {repo_id} --root {root} "
                f"--operation.type delete_episodes --operation.episode_indices '{bad}'"
            )
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
