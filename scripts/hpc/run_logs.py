"""From a laptop: what the training runs on the DTU cluster are doing, kept for the slides.

    uv run python scripts/hpc/run_logs.py                       # every run whose name starts with act_
    uv run python scripts/hpc/run_logs.py --match act_sock_v1   # only those

Reads each job's log and saved training config on the cluster (nothing is changed there), then
writes on this laptop:
  docs/figures/training_curves.png   the learning curves, one line per run
  docs/figures/training_curves.csv   the same numbers, one row per run and logged step
and prints a table of the runs (settings, progress, speed, GPU) to paste into the docs.
Run it again at any time: it rebuilds everything from the logs.

Needs the shared connection to the cluster (scripts/hpc/push_dataset.sh says how to open it).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_EVERY = 200  # lerobot-train logs one line every 200 steps

# Runs on the cluster. Python 3 standard library only.
REMOTE = r"""
import glob, json, os, re
store = os.environ["BLACKHOLE"] + "/makai/outputs"
runs = {}
for path in sorted(glob.glob(os.path.expanduser("~/MAKAI/makai_act_*.err"))):
    text = open(path, errors="replace").read()
    found = re.search(r"Output dir: \S+/outputs/(\S+)", text)
    if not found:
        continue
    run = found.group(1)
    curve = re.findall(
        r"INFO (\S+ \S+) \S+ step:\S+ smpl:\S+ ep:\S+ epch:(\S+) loss:(\S+) grdn:(\S+) lr:(\S+) data_s:\S+ "
        r"prep_s:\S+ updt_s:\S+ step_s:(\S+) smp/s:\S+ mem_gb:(\S+) l1_loss:(\S+) kld_loss:(\S+)", text)
    head = open(path[:-3] + "out", errors="replace").read().splitlines()[:1]
    steps = sorted(os.path.basename(p) for p in glob.glob(store + "/" + run + "/checkpoints/[0-9]*"))
    config = {}
    if steps:
        config = json.load(open(store + "/" + run + "/checkpoints/" + steps[-1] + "/pretrained_model/train_config.json"))
    runs[run] = {"job": re.search(r"makai_act_(\d+)", path).group(1), "node": head[0] if head else "",
                 "checkpoints": steps, "config": config, "curve": curve, "finished": "End of training" in text}
print("MAKAI_JSON" + json.dumps(runs))
"""

LABELS = {
    "": "reference",
    "_aug": "lighting augmentation",
    "_c50": "50-step chunks",
    "_wrist": "wrist camera only",
}
# Categorical colours in a fixed order, checked for colour-blind separation on this surface.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE, INK, SECONDARY, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e6e5e1"


def fetch(host: str) -> dict:
    ssh = ["ssh"]
    socket = Path.home() / ".ssh" / f"cm-{host}"
    if socket.exists():  # only for the host it was opened for
        ssh += ["-o", f"ControlPath={socket}"]
    done = subprocess.run([*ssh, host, 'bash -lc "python3 -"'], input=REMOTE, capture_output=True, text=True)
    lines = [line for line in done.stdout.splitlines() if line.startswith("MAKAI_JSON")]
    if not lines:
        raise SystemExit(
            f"Could not read the runs on {host}: is the shared connection open?\n{done.stderr[-400:]}"
        )
    return json.loads(lines[-1].removeprefix("MAKAI_JSON"))


def label(run: str, match: str) -> str:
    for suffix in sorted(LABELS, key=len, reverse=True):
        if suffix and run.endswith(suffix):
            return LABELS[suffix]
    return LABELS[""] if run == match else run


def smooth(values: list[float], window: int = 5) -> list[float]:
    """Mean of the last `window` logged values: one logged value is the loss of a single batch."""
    return [
        sum(values[max(0, i - window + 1) : i + 1]) / len(values[max(0, i - window + 1) : i + 1])
        for i in range(len(values))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--match", default="act_", help="keep the runs whose name starts with this")
    parser.add_argument("--name", default="training_curves", help="name of the figure and of the csv")
    parser.add_argument("--host", default=os.environ.get("HPC_HOST", "dtu"))
    args = parser.parse_args()

    runs = {
        name: run for name, run in fetch(args.host).items() if name.startswith(args.match) and run["curve"]
    }
    if not runs:
        raise SystemExit(f"No run starting with '{args.match}' has logged anything yet.")
    shortest = min(runs, key=len)
    figures = REPO_ROOT / "docs" / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    table = [
        "| Run | Dataset | Cameras | Chunk | Image augmentation | Steps done / asked | L1 error, first → latest | "
        "Seconds per step | GPU | Started | Checkpoints |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    with (figures / f"{args.name}.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "run",
                "step",
                "time",
                "epoch",
                "loss",
                "l1_loss",
                "kld_loss",
                "grad_norm",
                "lr",
                "step_s",
                "gpu_mem_gb",
            ]
        )
        for name, run in sorted(runs.items()):
            for i, (when, epoch, loss, grad, lr, step_s, mem, l1, kld) in enumerate(run["curve"]):
                writer.writerow(
                    [name, LOG_EVERY * (i + 1), when, epoch, loss, l1, kld, grad, lr, step_s, mem]
                )
            config, curve = run["config"], run["curve"]
            policy, dataset = config.get("policy", {}), config.get("dataset", {})
            cameras = [key.rsplit(".", 1)[-1] for key in policy.get("input_features", {}) if "images" in key]
            transforms = dataset.get("image_transforms", {})
            augmentation = ", ".join(transforms.get("tfs", {})) if transforms.get("enable") else "none"
            times = sorted(float(row[5]) for row in curve)
            gpu = run["node"].split("|")[1].split(",")[0].strip() if "|" in run["node"] else "?"
            table.append(
                f"| `{name}`{' (finished)' if run['finished'] else ''} | `{dataset.get('repo_id', '?')}` | {' + '.join(cameras) or '?'} | "
                f"{policy.get('chunk_size', '?')} | {augmentation} | {LOG_EVERY * len(curve):,} / {config.get('steps', 0):,} | "
                f"{float(curve[0][7]):.3f} → {float(curve[-1][7]):.3f} | {times[len(times) // 2]:.3f} | {gpu} | "
                f"{curve[0][0][5:16]} | {len(run['checkpoints'])} |".replace(",", " ")
            )
    print("\n".join(table))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "sans-serif", "font.size": 11})
    figure, axes = plt.subplots(figsize=(10, 5.2), dpi=160)
    figure.patch.set_facecolor(SURFACE)
    axes.set_facecolor(SURFACE)
    ends = []
    for colour, (name, run) in zip(SERIES, sorted(runs.items()), strict=False):
        steps = [LOG_EVERY * (i + 1) / 1000 for i in range(len(run["curve"]))]
        values = smooth([float(row[7]) for row in run["curve"]])
        axes.plot(
            steps,
            values,
            color=colour,
            linewidth=2,
            solid_capstyle="round",
            solid_joinstyle="round",
            label=label(name, shortest),
        )
        axes.plot(
            steps[-1],
            values[-1],
            "o",
            color=colour,
            markersize=8,
            markeredgecolor=SURFACE,
            markeredgewidth=2,
            zorder=3,
        )
        ends.append((values[-1], steps[-1], label(name, shortest)))
    axes.set_yscale("log")
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

    axes.yaxis.set_major_locator(
        FixedLocator([0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0])
    )  # plain numbers, not powers
    axes.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
    axes.yaxis.set_minor_formatter(NullFormatter())
    low, high = axes.get_ylim()
    place = low * (high / low) ** 0.97  # labels stacked from the top, so that they never overlap
    for value, step, text in sorted(ends, reverse=True):
        axes.annotate(f"{text}: {value:.3f} at {step:.0f}k", (0.985, 0), xycoords=("axes fraction", "data"), xytext=(0.985, place),
                      textcoords=("axes fraction", "data"), ha="right", va="top", color=INK, fontsize=10)  # fmt: skip
        place /= (high / low) ** 0.075
    axes.set_xlabel("Training steps (thousands)", color=SECONDARY)
    axes.set_ylabel("L1 error on normalised actions (log scale)", color=SECONDARY)
    axes.grid(True, which="major", color=GRID, linewidth=1)
    axes.grid(False, which="minor")
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        axes.spines[side].set_color(GRID)
    axes.tick_params(colors=MUTED, which="both", length=0)
    axes.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.12),
        ncol=len(runs),
        frameon=False,
        labelcolor=SECONDARY,
        handlelength=1.6,
    )
    figure.suptitle(
        "Training error of the pick policy, run by run",
        x=0.065,
        y=0.975,
        ha="left",
        color=INK,
        fontsize=14,
        fontweight="bold",
    )
    axes.set_title(
        f"ACT on {next(iter(runs.values()))['config'].get('dataset', {}).get('repo_id', '').split('makai_')[-1]}, "
        "mean of the last 5 logged values (one every 200 steps)",
        loc="left", color=SECONDARY, fontsize=10, pad=30,
    )  # fmt: skip
    figure.tight_layout(rect=(0, 0, 1, 0.97))
    figure.savefig(figures / f"{args.name}.png", facecolor=SURFACE)
    print(f"\nwrote docs/figures/{args.name}.png and docs/figures/{args.name}.csv")


if __name__ == "__main__":
    main()
