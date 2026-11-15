"""One command to collect demonstrations of one object.

    uv run python scripts/collect.py sock --try     # 2 episodes in a throwaway dataset: do this first
    uv run python scripts/collect.py sock           # 30 episodes into pick_sock_v1 (run again to add 30)
    uv run python scripts/collect.py can            # same for the can, into pick_can_v1

What it does, in order:
  1. checks the robot, both cameras, the leader arm and the loop time (scripts/preflight.py).
     If the robot does not answer, it prints the exact command to start the host on the Pi;
  2. records (scripts/record.py): a live view to check the cameras, then one episode at a time;
  3. zips the whole dataset onto your Desktop, ready to hand to whoever launches the training.

One episode: RIGHT ARROW -> GO -> recording starts when the leader moves -> saved once the arm
is back home and still for one second. LEFT ARROW cancels or drops, ESC ends the session.
The bottom line of the terminal and the status panel in Rerun say what to do at every step.
--manual: recording starts at the RIGHT ARROW itself and only the RIGHT ARROW saves.

Anything else on the line goes to record.py, for example:  --home-tol 15   or   --manual
`--dry-run` rehearses everything with a fake robot and leader.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from lerobot.utils.constants import HF_LEROBOT_HOME

from makai.config import load_config

SCRIPTS = Path(__file__).resolve().parent


def host_command(cfg: dict) -> str:
    """The command to run on the Pi, with every camera of the config."""
    robot = cfg["robot"]
    cameras = ", ".join(
        f"{name}: {{type: opencv, index_or_path: {cam['index_or_path']}, width: {cam['width']}, "
        f"height: {cam['height']}, fps: {cam.get('fps', robot['fps'])}, fourcc: MJPG, warmup_s: 3}}"
        for name, cam in robot["cameras"].items()
    )
    port = robot.get("base", {}).get("port", "/dev/ttyACM0")
    return (
        f"python ~/makai_host.py --arm_acceleration=50 --robot.id={robot['id']} --robot.port={port} "
        f"--robot.cameras='{{{cameras}}}' --host.connection_time_s=36000"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("object", help="what is picked up: sock or can")
    parser.add_argument("--episodes", type=int, default=None, help="default: 30, or 2 with --try")
    parser.add_argument("--name", default=None, help="dataset name; default: pick_<object>_v1")
    parser.add_argument("--try", dest="trial", action="store_true", help="2 episodes in a throwaway dataset")
    parser.add_argument("--dry-run", action="store_true", help="fake robot and leader: no hardware")
    args, for_record = parser.parse_known_args()

    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the sub-commands' output
    cfg = load_config()
    default = "essai" if args.trial else "repetition" if args.dry_run else "pick"
    name = args.name or (f"{default}_{args.object}" if default != "pick" else f"pick_{args.object}_v1")
    episodes = args.episodes or (2 if args.trial else 30)
    dry = ["--dry-run"] if args.dry_run else []

    print("== 1/3 checking the robot, the cameras and the leader ==")
    if subprocess.run([sys.executable, str(SCRIPTS / "preflight.py"), *dry]).returncode != 0:
        print("\nNot ready. If the robot does not answer or a camera is missing, the host is not running")
        print("with every camera. Close the control page (scripts/drive.py), then on the Pi:\n")
        print("  conda activate lerobot")
        print(f"  {host_command(cfg)}\n")
        print("Hold the arm when you stop a host: its motors go limp. Then run this command again.")
        raise SystemExit(1)

    print(f"\n== 2/3 recording {episodes} episodes of '{args.object}' into {name} ==")
    print("A Rerun window opens with the two cameras: a live view first, the recording starts after Enter.")
    print("The bottom line of this terminal says what to do; the Rerun window shows the same words.")
    record = [sys.executable, str(SCRIPTS / "record.py"), "--name", name, "--object", args.object]
    code = subprocess.run([*record, "--episodes", str(episodes), *dry, *for_record]).returncode

    namespace = cfg["hub"]["namespace"]
    if args.dry_run or namespace == "CHANGE_ME":
        namespace = "local"
    folder = Path(HF_LEROBOT_HOME) / namespace / f"makai_{name}"
    if args.trial:
        print(f"\nThis was a trial. Look at it, then delete it:  {folder}")
        print(f"If it looks right:  uv run python scripts/collect.py {args.object}")
        raise SystemExit(code)
    if not (folder / "data").exists():  # a session that died before its first save leaves only images
        raise SystemExit(f"No episode saved in {folder} (record.py exit code {code}): nothing to pack.")
    if code != 0:
        print(
            f"\nWARNING: record.py stopped with an error (exit code {code}). Packing the episodes saved before it."
        )

    print("\n== 3/3 packing the dataset ==")
    desktop = Path.home() / "Desktop"
    target = (desktop if desktop.exists() else Path.home()) / f"makai_{name}"
    archive = shutil.make_archive(str(target), "zip", root_dir=folder.parent, base_dir=folder.name)
    size_mb = Path(archive).stat().st_size / 1e6
    print(f"{archive}  ({size_mb:.0f} MB)")
    if args.dry_run:
        print("Rehearsal: nothing real was recorded. Delete this zip and", folder)
        raise SystemExit(code)
    print("Send this file (AirDrop, USB stick) to whoever launches the training on the cluster.")
    print(f"To add more episodes of '{args.object}', run the same command again: the zip is rebuilt whole.")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
