#!/usr/bin/env bash
# From a laptop: bring a model trained on the DTU HPC cluster back, ready for try_pick.py.
#
#   scripts/hpc/fetch_model.sh act_sock_v1            # the latest checkpoint
#   scripts/hpc/fetch_model.sh act_sock_v1 020000     # a given step
#   scripts/hpc/fetch_model.sh act_sock_v1 list       # which checkpoints exist
#
# The model lands in outputs/train/<run>/checkpoints/<step>/pretrained_model (about 200 MB).
# HPC_HOST: ssh name of the cluster (default: dtu). See push_dataset.sh for the shared connection.
set -euo pipefail
if [ "$#" -lt 1 ]; then sed -n '2,10p' "$0"; exit 1; fi
cd "$(dirname "$0")/../.."
RUN="$1"; STEP="${2:-last}"
HOST="${HPC_HOST:-dtu}"
SSH=(ssh); [ -S "$HOME/.ssh/cm-dtu" ] && SSH=(ssh -o "ControlPath=$HOME/.ssh/cm-dtu")
STORE=$("${SSH[@]}" "$HOST" 'bash -lc "echo \$BLACKHOLE"' 2>/dev/null | tail -1)
[ -n "$STORE" ] || { echo "Could not read \$BLACKHOLE on $HOST" >&2; exit 1; }
REMOTE="$STORE/makai/outputs/$RUN/checkpoints"
if [ "$STEP" = "list" ]; then
  "${SSH[@]}" "$HOST" "ls $REMOTE" 2>/dev/null | grep -E '^[0-9]+$|^last$' | tr '\n' ' '; echo; exit 0
fi
if [ "$STEP" = "last" ]; then   # `last` is a link on the cluster: name the real step
  STEP=$("${SSH[@]}" "$HOST" "ls $REMOTE" 2>/dev/null | grep -E '^[0-9]+$' | sort | tail -1)
  [ -n "$STEP" ] || { echo "No checkpoint yet for $RUN" >&2; exit 1; }
fi
DEST="outputs/train/$RUN/checkpoints/$STEP/pretrained_model"
mkdir -p "$DEST"
rsync -az -e "${SSH[*]}" "$HOST:$REMOTE/$STEP/pretrained_model/" "$DEST/"
echo "Fetched step $STEP. Try it with:"
echo "  uv run python scripts/try_pick.py --policy $DEST --trials 10"
