"""Record demonstrations on LeKiwi into a LeRobot dataset.

    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30
    uv run python scripts/record.py --name pick_sock_v1 --object sock --episodes 30     # adds 30 more

Run it again with the same --name to ADD episodes: nothing is overwritten, and a crash loses
at most the episode being recorded. The dataset is pushed to the Hub when a session ends.

A live view opens first (Rerun: both cameras, the arm follows the leader, nothing is recorded):
set the scene, check the pictures, put the leader on its rest and press Enter. The pose of the
arm at that moment is "home": every episode starts from it and comes back to it. It is kept
with the dataset by its first session, and a later session that starts elsewhere is told so.

One episode, the pilot in charge of when it begins:
  1. place the object, then RIGHT ARROW: the recorder says GO, nothing is recorded yet;
  2. recording starts when the leader moves (no dead time at the start);
  3. the episode is saved once the arm has left home, is back home, and has stayed still for
     one second. The status line says when the arm is seen at home and counts that second.
  RIGHT ARROW  get ready for an episode; while recording: save it now
  LEFT ARROW   cancel, or drop the episode being recorded; just after a save: mark it as bad
  ESC          end the session (an episode being recorded is dropped)
Nothing is ever recorded outside RECORDING, and nothing starts without the RIGHT ARROW.
--manual: recording starts at the RIGHT ARROW itself and only the RIGHT ARROW saves.

What the pilot must read is one status: the bottom line of this terminal and the "status"
panel of the Rerun window show the same words. What happened (saved, not saved and why) stays
above it as one line per episode, starting with [saved in this session / asked].

    uv run python scripts/record.py --name rehearsal --object sock --episodes 2 --dry-run

--dry-run rehearses the whole session with a fake robot and leader (no hardware, nothing
uploaded): use it to check the laptop before the robot is free.

Protocol and quality rules: docs/DATA_COLLECTION.md. Tonight's plan: docs/CE_SOIR.md.
"""

import argparse
import contextlib
import csv
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml
from lerobot.datasets import LeRobotDataset
from lerobot.lerobot_types import TransitionKey
from lerobot.teleoperators.so_leader import SO101Leader, SO101LeaderConfig
from lerobot.utils.constants import ACTION, HF_LEROBOT_HOME, OBS_STR
from lerobot.utils.feature_utils import build_dataset_frame, hw_to_dataset_features
from lerobot.utils.keyboard_input import init_keyboard_listener
from lerobot.utils.robot_utils import precise_sleep
from lerobot.utils.utils import log_say
from lerobot.utils.visualization_utils import init_visualization, log_visualization_data

from makai.config import CONFIG_DIR, REPO_ROOT, load_config
from makai.manipulation.skills import load_poses
from makai.robot.lekiwi import ARM_KEYS, make_client

STOP = {"x.vel": 0.0, "y.vel": 0.0, "theta.vel": 0.0}
# The gripper is left out of "is the arm home?": it is open at the start and closed at the end.
ARM = [key for key in ARM_KEYS if "gripper" not in key]


HOME_FILE = "makai_home.yaml"  # in the dataset folder: the home pose of its first session
KEY_PAUSE_S = 0.7  # after a key or a save, ignore the keys this long: a key held down repeats
MIN_KEY_EPISODE_S = 1.0  # an episode stopped by the key sooner than this is a double press

HELP = {
    False: """
HOW THIS SESSION WORKS
  1. Place the object. Leader on its rest, hands off.
  2. RIGHT ARROW: the recorder says GO. Nothing is recorded yet.
  3. Pick the object up: recording starts when you move the leader.
  4. Bring the leader back on its rest and hold still one second: the episode is saved.
     The status line says when the arm is seen at home, and counts that second.
  Then RIGHT ARROW for the next one. Nothing is recorded in between: take your time.
     RIGHT ARROW   get ready for an episode / while recording: save it now
     LEFT ARROW    cancel, or drop the episode being recorded (just after a save: mark it as bad)
     ESC           end the session
  To end every episode with the RIGHT ARROW instead, run with --manual.""",
    True: """
HOW THIS SESSION WORKS  (manual mode)
  1. Place the object. Leader on its rest.
  2. RIGHT ARROW: recording starts at once. Pick the object up, come back to the rest.
  3. RIGHT ARROW again: the episode is saved.
  Nothing is recorded in between: take your time.
     RIGHT ARROW   start / stop and save
     LEFT ARROW    drop the episode being recorded (just after a save: mark it as bad)
     ESC           end the session""",
}


@contextlib.contextmanager
def quiet(log_path: Path):
    """Send what this process and the ones it starts write to the terminal into a file instead.

    Saving an episode starts the video encoders, and they print some fifty lines each time:
    the pilot's status was buried under them.

    Not on Windows: there, sys.stdout and sys.stderr write to the console itself, and once the
    descriptors point to a file every write fails ("The handle is invalid"), which killed the
    process in the middle of the first save (15 Nov). The encoders' lines stay on screen there.
    """
    if sys.platform == "win32":
        yield
        return
    sys.stdout.flush()
    sys.stderr.flush()
    terminal = os.dup(1), os.dup(2)
    with open(log_path, "ab") as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        try:
            yield
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(terminal[0], 1)
            os.dup2(terminal[1], 2)
            os.close(terminal[0])
            os.close(terminal[1])


class Screen:
    """Permanent lines for what happened, and one line at the bottom, redrawn in place, for what
    is happening now. Without a real terminal (a log file) that line is printed when its
    `key` changes, not at every change of a number."""

    def __init__(self) -> None:
        self.tty = sys.stdout.isatty()
        self.shown = ""

    def line(self, text: str) -> None:
        if self.tty and self.shown:
            sys.stdout.write("\r" + " " * len(self.shown) + "\r")
        print(text, flush=True)
        self.shown = ""

    def now(self, text: str, key: str) -> None:
        if not self.tty:
            if key != self.shown:
                print(text, flush=True)
                self.shown = key
            return
        text = text[: shutil.get_terminal_size().columns - 1]
        if text != self.shown:
            sys.stdout.write("\r" + text.ljust(len(self.shown)))
            sys.stdout.flush()
            self.shown = text


def read_keys(events: dict) -> tuple[bool, bool]:
    """(RIGHT, LEFT) pressed since the last call, then cleared: a key must never act twice.

    LeRobot raises "exit_early" for every key, so on its own it means the RIGHT ARROW. Left
    raised, it would save the next episode on its first frame.
    """
    right = events["exit_early"] and not events["rerecord_episode"] and not events["stop_recording"]
    left = events["rerecord_episode"]
    events["exit_early"] = events["rerecord_episode"] = False
    return right, left


def rehearsal_key(state: str, idle_for: float, recording_for: float, manual: bool) -> bool:
    """--dry-run: the RIGHT ARROW a pilot would press, one second after an episode, and in
    manual mode after three seconds of recording."""
    return (state == "idle" and idle_for > 1.0) or (manual and state == "recording" and recording_for > 3.0)


def decide(
    state: str,
    *,
    manual: bool,
    right: bool,
    left: bool,
    moved: bool,
    back_home: bool,
    elapsed: float,
    min_episode: float,
    max_episode: float,
) -> str:
    """What happens on this tick: "" (nothing), "arm", "cancel", "start", "save", or why the
    episode is dropped.

    idle -> (RIGHT ARROW) -> armed -> (the leader moves) -> recording -> (the arm is back home,
    still) -> saved, idle again. Nothing starts without the RIGHT ARROW: a recorder that armed
    itself restarted in a loop whenever the leader's rest was a few degrees off. `back_home`
    must be false until the arm has left home: the real arm trails the leader, so when an
    episode starts it is still at home and still. In manual mode the RIGHT ARROW starts the
    recording itself and only the RIGHT ARROW saves.
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
    if state == "armed":
        if left:
            return "cancel"
        return "start" if right or moved else ""
    if right:
        return "start" if manual else "arm"
    return ""


def status(
    state: str,
    *,
    manual: bool,
    elapsed: float = 0.0,
    limit: float = 0.0,
    at_home: bool = True,
    far: str = "",
    still: float = 0.0,
    need: float = 1.0,
    left_home: bool = False,
) -> tuple[str, str]:
    """What the pilot must read now: a headline and one line of detail.

    The terminal and the Rerun panel show exactly these words, so they cannot disagree.
    """
    home = "arm at home" if at_home else f"arm NOT at home: {far}"
    if state == "live":
        return "LIVE VIEW", "nothing is recorded. Leader on its rest, hands off, then press Enter"
    if state == "idle":
        if manual:
            return "PRESS RIGHT ARROW", f"to start recording   [{home}]"
        if not at_home:
            return "PUT THE LEADER ON ITS REST", f"{far} from home   [RIGHT ARROW = start anyway]"
        return (
            "PRESS RIGHT ARROW",
            "once the object is placed. Recording will start when you move   [arm at home]",
        )
    if state == "armed":
        return "GO", "recording starts when you move the leader   [LEFT ARROW = cancel]"
    headline = f"RECORDING {elapsed:.0f} s"
    if manual:
        return headline, f"RIGHT ARROW = stop and save, LEFT ARROW = drop   [{home}]"
    if not left_home:
        detail = "pick the object up, then bring the leader back on its rest"
    elif not at_home:
        detail = f"bring the leader back on its rest ({home})"
    else:
        detail = f"AT HOME: hold still {min(still, need):.1f} / {need:.1f} s"
    return headline, f"{detail}   [max {limit:.0f} s, RIGHT ARROW = save now, LEFT ARROW = drop]"


def status_panel(headline: str, detail: str, last: str, recorded: int, asked: int, total: int) -> dict:
    """The status as a text panel in Rerun, next to the cameras.

    LeRobot's viewer lays out a text panel for a policy's predicted text: we pass ours that way.
    """
    text = (
        f"{headline}\n{detail}\n\nLast episode: {last}\n"
        f"Saved in this session: {recorded} of {asked}\nEpisodes in the dataset: {total}"
    )
    return {TransitionKey.PREDICTION: {"language": {"status": [text]}}}


def check_home(pose: dict[str, float], dataset_root: Path, tol: float, say) -> None:
    """One home pose per dataset, and the same one on the robot.

    "Home" is where the arm is when the leader sits on its rest: the pose every episode starts
    from and comes back to. Each session measures it again. The first session of a dataset
    writes it into the dataset folder and later sessions are compared with it: a rest that has
    moved would make the new episodes start from another pose. It is also compared with `home`
    in the poses file, the pose the mission puts the arm in before every pick.
    """

    def gap(reference: dict) -> tuple[str, float]:  # the joint that differs most, and by how much
        key = max(ARM, key=lambda k: abs(pose[k] - float(reference.get(k, 0.0))))
        return key, pose[key] - float(reference.get(key, 0.0))

    line = yaml.safe_dump(pose, default_flow_style=True, width=1000).strip()
    kept = dataset_root / HOME_FILE
    if not kept.exists():
        kept.write_text(line + "\n")
        print(f"First session of this dataset: this is now its home pose (kept in {kept}).")
    else:
        key, degrees = gap(yaml.safe_load(kept.read_text()))
        if abs(degrees) <= tol:
            print(
                f"Same home pose as the first session of this dataset (largest gap: {abs(degrees):.0f} degrees)."
            )
        else:
            say("Home pose differs", f"{key} is {degrees:+.0f} degrees from this dataset's first session (tolerance {tol:.0f})")  # fmt: skip
            print("  The new episodes would start from another pose than the earlier ones.")
            print(
                "  ESC, put the leader's rest back where it was, and run again. Or carry on if this is wanted."
            )

    poses_file = CONFIG_DIR / load_config()["manipulation"]["poses_file"]
    robot_home = load_poses(poses_file).get("home", {})
    key, degrees = gap(robot_home)
    if abs(degrees) > tol:
        unset = not any(abs(float(value)) > 1e-6 for value in robot_home.values())
        print(
            f"The mission does not know this home pose yet ({poses_file.name} still holds the placeholder)."
            if unset
            else f"The mission's home pose is another one: {key} differs by {degrees:+.0f} degrees."
        )
        print(
            f"  The policy must start every pick from the pose it was trained from. In configs/{poses_file.name}:"
        )
        print(f"  home: {line}")
        print("  (no gripper in it: going home must not open the hand that holds the object)")


def session(robot, leader, dataset, events, args, fps, task, display, say, screen, save, on_saved, on_bad):
    """Record episodes: armed by the pilot, started by the leader moving, saved back at home."""
    total = dataset.meta.total_episodes
    names = [key.removeprefix("arm_").removesuffix(".pos") for key in ARM]
    recent: deque = deque(maxlen=2 * fps)  # the last two seconds of arm positions
    preroll: deque = deque(maxlen=fps // 4)  # frames from just before the leader moved

    def tick():
        observation = robot.get_observation()
        leader_action = leader.get_action()
        action = {**{f"arm_{key}": value for key, value in leader_action.items()}, **STOP}
        robot.send_action(action)
        arm = np.array([float(observation[key]) for key in ARM])
        hand = np.array([float(leader_action[key.removeprefix("arm_")]) for key in ARM])
        return observation, action, arm, hand

    def still_seconds() -> float:
        """For how long the arm has not moved, up to the two seconds remembered."""
        low = high = None
        count = 0
        for sample in reversed(recent):
            low = sample if low is None else np.minimum(low, sample)
            high = sample if high is None else np.maximum(high, sample)
            if float((high - low).max()) >= args.still_tol:
                break
            count += 1
        return count / fps

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
    print("Then press Enter (or the RIGHT ARROW): the pose of the arm at that moment becomes home.")
    go = threading.Event()
    if args.dry_run:
        threading.Timer(1.5, go.set).start()
    else:
        threading.Thread(target=lambda: (input(), go.set()), daemon=True).start()
    headline, detail = status("live", manual=args.manual)
    while not go.is_set() and not events["exit_early"] and not events["stop_recording"]:
        start = time.perf_counter()
        observation, action, _, _ = tick()
        if display:
            panel = status_panel(headline, detail, "none yet", 0, args.episodes, total)
            log_visualization_data("rerun", observation=observation, action=action, policy_step=panel)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))
    events["exit_early"] = False

    # Home: the arm trails the leader, so wait until it has stopped, then average half a second.
    print("Measuring the home pose: do not touch the leader...")
    hands: deque = deque(maxlen=fps // 2)
    deadline = time.perf_counter() + 10.0
    while still_seconds() < 1.0 and time.perf_counter() < deadline:
        start = time.perf_counter()
        _, _, arm, hand = tick()
        recent.append(arm)
        hands.append(hand)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))
    if still_seconds() < 1.0:
        print("WARNING: the arm did not stay still for one second: this home pose may be wrong.")
        print("  ESC, then run again with the leader resting on its support, hands off.")
    home_arm = np.mean(list(recent)[-(fps // 2) :], axis=0)
    home_hand = np.mean(hands, axis=0)
    print("Home pose:", ", ".join(f"{name} {value:.0f}" for name, value in zip(names, home_arm, strict=True)))
    check_home(
        {key: round(float(value), 1) for key, value in zip(ARM, home_arm, strict=True)},
        Path(dataset.root),
        args.home_tol,
        say,
    )
    print()

    state, recorded, started, saved_at, quiet_until = "idle", 0, 0.0, -1e9, 0.0
    left_home, armed_hand, idle_since, last = False, home_hand, time.perf_counter(), "none yet"
    while recorded < args.episodes and not events["stop_recording"]:
        start = time.perf_counter()
        observation, action, arm, hand = tick()
        recent.append(arm)
        frame = {
            **build_dataset_frame(dataset.features, observation, prefix=OBS_STR),
            **build_dataset_frame(dataset.features, action, prefix=ACTION),
            "task": task,
        }
        # A key held down repeats, and keys pressed while an episode is written pile up.
        right, left = read_keys(events)
        if start < quiet_until:
            right = left = False
        elif right or left:
            quiet_until = start + KEY_PAUSE_S
        gaps = np.abs(arm - home_arm)
        at_home = float(gaps.max()) < args.home_tol
        far = f"{names[int(gaps.argmax())]} is {gaps.max():.0f} degrees away"
        if args.dry_run and at_home:  # nobody is there to press the keys
            right = right or rehearsal_key(state, start - idle_since, start - started, args.manual)
        still = still_seconds()
        elapsed = start - started if state == "recording" else 0.0
        left_home = left_home or (state == "recording" and not at_home)

        if left and state == "idle":
            if recorded > 0 and start - saved_at < 20.0:
                on_bad()
                last = "saved, then marked as bad"
                say("Marked as bad", "the last episode: it is listed at the end, to remove before training")
                saved_at = -1e9
            else:
                say("Nothing to drop", "no episode is being recorded", speak=False)

        step = decide(
            state,
            manual=args.manual,
            right=right,
            left=left,
            moved=float(np.abs(hand - armed_hand).max()) > args.leave_tol,
            back_home=left_home and at_home and still >= args.end_still,
            elapsed=elapsed,
            min_episode=args.min_episode,
            max_episode=args.episode_time,
        )
        if state == "armed":
            preroll.append(frame)
        if step == "arm":
            state, armed_hand = "armed", hand  # "moved" is measured from where the leader is now
            preroll.clear()
            say("Go", show=False)
        elif step == "cancel":
            state, idle_since = "idle", start
        elif step == "start":
            # Started by the leader moving: keep the quarter second before it. By the key: from now.
            for earlier in list(preroll) if state == "armed" and not right else [frame]:
                dataset.add_frame(earlier)
            state, started, left_home = "recording", start, not at_home
        elif state == "recording":
            dataset.add_frame(frame)
            if step == "save":
                screen.now(f"[{recorded:>2}/{args.episodes}] SAVING: wait a moment", "saving")
                save()
                recorded += 1
                saved_at = time.perf_counter()
                on_saved(elapsed)
                total = dataset.meta.total_episodes
                last = f"saved, {elapsed:.1f} s"
                say("Saved", f"{elapsed:.1f} s. The dataset now holds {total} episodes", speak=f"{recorded}")
            elif step:
                dataset.clear_episode_buffer()
                why = {
                    "Too long": f"over {args.episode_time:.0f} s (see --episode-time)",
                    "Too short": f"stopped in under {MIN_KEY_EPISODE_S:.0f} s: a double press?",
                    "False start": f"back on the rest in under {args.min_episode:.0f} s",
                    "Dropped": "LEFT ARROW",
                }[step]
                last = f"NOT saved: {why}"
                say("Not saved", f"{why}. RIGHT ARROW for the next try", speak=step)
            if step:
                state, idle_since = "idle", time.perf_counter()
                quiet_until = idle_since + KEY_PAUSE_S

        headline, detail = status(
            state,
            manual=args.manual,
            elapsed=elapsed,
            limit=args.episode_time,
            at_home=at_home,
            far=far,
            still=still,
            need=args.end_still,
            left_home=left_home,
        )
        if recorded < args.episodes:
            screen.now(f"[{recorded:>2}/{args.episodes}] {headline}: {detail}", state)
        if display:
            panel = status_panel(headline, detail, last, recorded, args.episodes, total)
            log_visualization_data("rerun", observation=observation, action=action, policy_step=panel)
        precise_sleep(max(0.0, 1.0 / fps - (time.perf_counter() - start)))

    if state == "recording":
        dataset.clear_episode_buffer()
        say("Not saved", "the session ended during an episode", speak=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--name", required=True, help="dataset name, e.g. pick_sock_v1")
    parser.add_argument("--object", required=True, help="what is being picked up: sock, can...")
    parser.add_argument("--episodes", type=int, default=30, help="episodes to record in this session")
    parser.add_argument("--episode-time", type=float, default=30.0, help="seconds: longer is dropped")
    parser.add_argument("--task", default=None, help="default: 'Pick up the <object> from the floor'")
    parser.add_argument("--no-push", action="store_true", help="keep the dataset on this laptop")
    parser.add_argument("--no-display", action="store_true", help="do not open Rerun (if the loop is slow)")
    parser.add_argument("--dry-run", action="store_true", help="fake robot and leader: no hardware")
    parser.add_argument("--manual", action="store_true", help="the RIGHT ARROW starts and saves each episode")
    parser.add_argument(
        "--home-tol", type=float, default=10.0, help="degrees from home that still count as home"
    )
    parser.add_argument(
        "--leave-tol", type=float, default=5.0, help="degrees of leader motion that start an episode"
    )
    parser.add_argument(
        "--still-tol", type=float, default=2.0, help="degrees the arm may move and still be 'still'"
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
        robot.lag_ticks = 12  # like the real arm, 0.4 s behind the leader
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
    display = not args.no_display
    if display:
        init_visualization("rerun", session_name="makai_record")

    log_path = REPO_ROOT / "outputs" / "recordings" / f"{args.name}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    first_episode = dataset.meta.total_episodes
    bad: list[int] = []
    started = time.time()

    screen = Screen()

    def say(text: str, hint: str = "", speak: str | bool = True, show: bool = True) -> None:
        """Keep a line for what just happened, and speak it: the voice alone is easy to miss.

        The line starts with the number of episodes saved in this session."""
        saved = dataset.meta.total_episodes - first_episode
        if show:
            screen.line(f"[{saved:>2}/{args.episodes}] {text.upper():<14} {hint}")
        if speak:
            log_say(text if speak is True else speak, play_sounds=not args.dry_run)

    def save() -> None:  # the encoders' chatter goes to a file next to the episode list
        with quiet(log_path.with_suffix(".log")):
            dataset.save_episode()

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
        session(robot, leader, dataset, events, args, fps, task, display, say, screen, save, on_saved, on_bad)
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
