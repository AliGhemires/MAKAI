"""Record demonstrations on LeKiwi into a LeRobot dataset.

    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30
    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30     # adds 30 more

Run it again with the same --name to ADD episodes: nothing is overwritten, and a crash loses
at most the episode being recorded. The dataset is pushed to the Hub when a session ends.

A live view opens first (Rerun: both cameras, the arm follows the leader, nothing is recorded):
set the scene, check the pictures, put the leader on its rest and press Enter.

Two modes. In both, nothing is recorded outside RECORDING, and the keys are the same:
  RIGHT ARROW  start an episode now, or stop it and save it now
  LEFT ARROW   drop the episode being recorded; just after a save: mark that episode as bad
  ESC          end the session (an episode being recorded is dropped)

Automatic (default): both hands stay on the job.
  1. READY when the arm is on its rest ("home") and still: place the object;
  2. recording starts by itself when the leader moves;
  3. the episode is saved by itself once the arm is back home and still for one second.
  Every episode starts from the same pose, has no dead time at the start, and ends with the
  same second of stillness. If READY never comes, the arm does not settle within the
  tolerance: press the RIGHT ARROW to start anyway, or raise --home-tol.

--manual: the pilot decides. RIGHT ARROW starts the episode, RIGHT ARROW saves it.

Where the session stands is always on screen: every line in this terminal starts with
[saved in this session / asked], and the Rerun window has a "status" panel next to the cameras
(WAIT, READY or RECORDING, the count, the size of the dataset). It is also spoken.

    uv run python scripts/record.py --name rehearsal --object sock --episodes 2 --dry-run

--dry-run rehearses the whole session with a fake robot and leader (no hardware, nothing
uploaded): use it to check the laptop before the robot is free.

Protocol and quality rules: docs/DATA_COLLECTION.md. Tonight's plan: docs/CE_SOIR.md.
"""

import argparse
import csv
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from lerobot.datasets import LeRobotDataset
from lerobot.lerobot_types import TransitionKey
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


KEY_PAUSE_S = 0.7  # after a key or a save, ignore the keys this long: a key held down repeats
MIN_KEY_EPISODE_S = 1.0  # an episode stopped by the key sooner than this is a double press

HELP = {
    False: """
HOW THIS SESSION WORKS  (automatic mode)
  1. READY shows when the leader is on its rest and still. Place the object.
  2. Pick it up: recording starts by itself as soon as you move the leader.
  3. Put the leader back on its rest and hold still one second: the episode is saved.
  Nothing is recorded outside RECORDING, so take your time between episodes.
     RIGHT ARROW   start now / stop and save now
     LEFT ARROW    drop the episode being recorded (just after a save: mark that one as bad)
     ESC           end the session
  To decide every start and stop yourself, run with --manual.""",
    True: """
HOW THIS SESSION WORKS  (manual mode: you decide)
  1. Place the object, leader on its rest.
  2. RIGHT ARROW: recording starts. Pick the object up and come back to the rest.
  3. RIGHT ARROW again: the episode is saved.
  Nothing is recorded outside RECORDING, so take your time between episodes.
     RIGHT ARROW   start / stop and save
     LEFT ARROW    drop the episode being recorded (just after a save: mark that one as bad)
     ESC           end the session""",
}
READY_HINT = {
    False: "place the object, then move the leader: recording starts by itself",
    True: "place the object, then RIGHT ARROW to start recording",
}
RECORDING_HINT = {
    False: "back on the rest and still = saved | RIGHT ARROW = save now | LEFT ARROW = drop",
    True: "RIGHT ARROW = stop and save | LEFT ARROW = drop",
}


def read_keys(events: dict) -> tuple[bool, bool]:
    """(RIGHT, LEFT) pressed since the last call, then cleared: a key must never act twice.

    LeRobot raises "exit_early" for every key, so on its own it means the RIGHT ARROW. Left
    raised, it would save the next episode on its first frame.
    """
    right = events["exit_early"] and not events["rerecord_episode"] and not events["stop_recording"]
    left = events["rerecord_episode"]
    events["exit_early"] = events["rerecord_episode"] = False
    return right, left


def decide(
    state: str,
    *,
    manual: bool,
    right: bool,
    left: bool,
    settled: bool,
    moved: bool,
    back_home: bool,
    elapsed: float,
    min_episode: float,
    max_episode: float,
) -> str:
    """What happens on this tick: "" (nothing), "ready", "start", "save", or why the episode is dropped.

    The RIGHT ARROW starts an episode, or stops and saves it; the LEFT ARROW drops it. In
    automatic mode an episode also starts when the leader leaves its rest (`moved`) and is
    saved once the arm is back on it and still (`back_home`).
    """
    if state == "recording":
        if left:
            return "Dropped"
        if elapsed > max_episode:
            return "Too long"
        if right:
            return "save" if elapsed >= MIN_KEY_EPISODE_S else "Too short"
        if not manual and back_home:
            return "save" if elapsed >= min_episode else "False start"
        return ""
    if right:
        return "start"
    if state == "reset":
        return "ready" if manual or settled else ""
    return "start" if not manual and moved else ""


def status_panel(
    state: str, manual: bool, recorded: int, asked: int, total: int, elapsed: float = 0.0, limit: float = 0.0
) -> dict:
    """Where the session stands, as a text panel in Rerun next to the cameras.

    LeRobot's viewer lays out a text panel for a policy's predicted text: we pass ours that way.
    """
    if state == "live":
        what = "LIVE VIEW: nothing is recorded yet.\nPut the leader on its rest, hands off, then press Enter."
    elif state == "recording":
        what = (
            f"RECORDING   {elapsed:.0f} s   (dropped after {limit:.0f} s)\n"
            + (
                "RIGHT ARROW = stop and save"
                if manual
                else "back on the rest and still = saved   (RIGHT ARROW = save now)"
            )
            + "\nLEFT ARROW = drop this episode"
        )
    elif state == "armed":
        what = "READY: place the object, then " + (
            "press the RIGHT ARROW to start." if manual else "move the leader. Recording starts by itself."
        )
    else:
        what = "WAIT: put the leader back on its rest and let go.   (RIGHT ARROW = start anyway)"
    text = f"{what}\n\nSaved in this session: {recorded} of {asked}\nEpisodes in the dataset: {total}"
    return {TransitionKey.PREDICTION: {"language": {"status": [text]}}}


def session(robot, leader, dataset, events, args, fps, task, display, say, on_saved, on_bad):
    """Record episodes, started and ended by the pilot's keys or by themselves (module docstring)."""
    total = dataset.meta.total_episodes

    def tick():
        observation = robot.get_observation()
        leader_action = leader.get_action()
        action = {**{f"arm_{key}": value for key, value in leader_action.items()}, **STOP}
        robot.send_action(action)
        arm = np.array([float(observation[key]) for key in ARM])
        hand = np.array([float(leader_action[key.removeprefix("arm_")]) for key in ARM])
        return observation, action, arm, hand

    # Live view first: the arm follows the leader and both cameras show in Rerun, so the
    # operator can set the scene and check the pictures before anything is recorded.
    if not args.dry_run:
        input(
            "\nPut the leader in about the same pose as the robot arm (the arm will follow it), then press Enter... "
        )
    print(
        "\nLIVE VIEW: the arm follows the leader, nothing is recorded yet."
        + (" Both cameras are in the Rerun window." if display else "")
    )
    print(HELP[args.manual])
    print("  If the keys do nothing, click on this terminal once.\n")
    print("Check the two pictures, put the leader on its rest in the home pose, hands off.")
    print("Then press Enter (or the RIGHT ARROW) to start.")
    go = threading.Event()
    if args.dry_run:
        threading.Timer(1.5, go.set).start()
    else:
        threading.Thread(target=lambda: (input(), go.set()), daemon=True).start()
    while not go.is_set() and not events["exit_early"] and not events["stop_recording"]:
        start = time.perf_counter()
        observation, action, _, _ = tick()
        if display:
            panel = status_panel("live", args.manual, 0, args.episodes, total)
            log_visualization_data("rerun", observation=observation, action=action, policy_step=panel)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))
    events["exit_early"] = False

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

    state, recorded, started, saved_at, quiet_until = "reset", 0, 0.0, -1e9, 0.0
    while recorded < args.episodes and not events["stop_recording"]:
        start = time.perf_counter()
        observation, action, arm, hand = tick()
        recent.append(arm)
        frame = {
            **build_dataset_frame(dataset.features, observation, prefix=OBS_STR),
            **build_dataset_frame(dataset.features, action, prefix=ACTION),
            "task": task,
        }
        right, left = read_keys(events)
        if start < quiet_until:
            right = left = False
        elif right or left:
            quiet_until = start + KEY_PAUSE_S
        at_home = float(np.abs(arm - home_arm).max()) < args.home_tol
        elapsed = start - started if state == "recording" else 0.0

        if left and state != "recording":
            if recorded > 0 and start - saved_at < 20.0:
                on_bad()
                say("Marked as bad", "the last episode: it is listed at the end, to remove before training")
                saved_at = -1e9
            else:
                say("Nothing to drop", "no episode is being recorded", speak=False)

        step = decide(
            state,
            manual=args.manual,
            right=right,
            left=left,
            settled=at_home and still_for(0.5),
            moved=float(np.abs(hand - home_hand).max()) > args.leave_tol,
            back_home=at_home and still_for(args.end_still),
            elapsed=elapsed,
            min_episode=args.min_episode,
            max_episode=args.episode_time,
        )
        if state == "armed":
            preroll.append(frame)
        if step == "ready":
            state = "armed"
            preroll.clear()
            say("Ready", READY_HINT[args.manual])
        elif step == "start":
            # Started by the leader moving: keep the quarter second before it. By the key: from now.
            for earlier in [frame] if right else list(preroll):
                dataset.add_frame(earlier)
            state, started = "recording", start
            say("Recording", RECORDING_HINT[args.manual], speak=False)
        elif state == "recording":
            dataset.add_frame(frame)
            if step == "save":
                dataset.save_episode()
                recorded += 1
                saved_at = time.perf_counter()
                on_saved(elapsed)
                total = dataset.meta.total_episodes
                say("Saved", f"{elapsed:.1f} s. The dataset now holds {total} episodes", speak=f"{recorded}")
            elif step:
                dataset.clear_episode_buffer()
                why = {
                    "Too long": f" (over {args.episode_time:.0f} s, see --episode-time)",
                    "Too short": f" (stopped in under {MIN_KEY_EPISODE_S:.0f} s: a double press?)",
                    "False start": f" (back on the rest in under {args.min_episode:.0f} s)",
                }.get(step, "")
                say(step, "not saved" + why)
            if step:
                recent.clear()
                state = "reset"
                quiet_until = time.perf_counter() + KEY_PAUSE_S

        if display:
            panel = status_panel(
                state, args.manual, recorded, args.episodes, total, elapsed, args.episode_time
            )
            log_visualization_data("rerun", observation=observation, action=action, policy_step=panel)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))

    if state == "recording":
        dataset.clear_episode_buffer()
        say("Dropped", "the session ended during an episode: it is not saved", speak=False)


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
    parser.add_argument("--manual", action="store_true", help="you start and stop every episode: RIGHT ARROW")
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
        from makai.robot.fake import FakeKiwi, FakeLeader

        robot = FakeKiwi(make_client(cfg).config)
        leader = FakeLeader(SO101LeaderConfig(port="none", id="fake_leader"))
    else:
        robot = make_client(cfg)
        leader = SO101Leader(
            SO101LeaderConfig(port=cfg["teleop"]["leader_port"], id=cfg["teleop"]["leader_id"])
        )

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
    listener, events = init_keyboard_listener()
    if args.dry_run and args.manual:  # nobody is there to press the keys: RIGHT ARROW every 3 s

        def press() -> None:
            while True:
                time.sleep(3.0)
                events["exit_early"] = True

        threading.Thread(target=press, daemon=True).start()
    display = not args.no_display
    if display:
        init_visualization("rerun", session_name="makai_record")

    log_path = REPO_ROOT / "outputs" / "recordings" / f"{args.name}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    first_episode = dataset.meta.total_episodes
    bad: list[int] = []
    started = time.time()

    def say(text: str, hint: str = "", speak: str | bool = True) -> None:
        """Show and speak what the recorder is doing: the voice alone is easy to miss.

        The line starts with the number of episodes saved in this session."""
        saved = dataset.meta.total_episodes - first_episode
        print(f"[{saved:>2}/{args.episodes}] {text.upper():<14} {hint}", flush=True)
        if speak:
            log_say(text if speak is True else speak, play_sounds=not args.dry_run)

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
        session(robot, leader, dataset, events, args, fps, task, display, say, on_saved, on_bad)
    finally:
        say("Session finished")
        robot.disconnect()
        leader.disconnect()
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
