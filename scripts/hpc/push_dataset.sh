#!/usr/bin/env bash
# From a laptop: copy a recorded dataset to the DTU HPC cluster, where the training jobs read
# it. No Hugging Face account needed.
#
#   scripts/hpc/push_dataset.sh pick_sock_v1
#
# then, on the cluster:  scripts/hpc/submit.sh pick_sock_v1 act_sock_v1 STEPS=100000
#
# Run it again after adding episodes: only what changed is sent.
# HPC_HOST is the ssh name of the cluster (default: dtu, as in ~/.ssh/config). To type the
# password only once for the whole evening, open a shared connection first:
#   ssh -o ControlMaster=yes -o ControlPath=~/.ssh/cm-dtu -o ControlPersist=8h -fN dtu
set -euo pipefail
if [ "$#" -lt 1 ]; then sed -n '2,13p' "$0"; exit 1; fi
cd "$(dirname "$0")/../.."
HOST="${HPC_HOST:-dtu}"
# The shared connection ~/.ssh/cm-<host> answers whatever host name ssh is given: only use it
# for the host it was opened for.
SSH=(ssh); [ -S "$HOME/.ssh/cm-$HOST" ] && SSH=(ssh -o "ControlPath=$HOME/.ssh/cm-$HOST")
NS="${HUB_NAMESPACE:-$(uv run --no-sync python -c "from makai.config import load_config; print(load_config()['hub']['namespace'])")}"
[ "$NS" = "CHANGE_ME" ] && NS=local
SRC="${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/${NS}/makai_$1"
[ -d "$SRC" ] || { echo "Dataset not found on this laptop: $SRC" >&2; exit 1; }
STORE=$("${SSH[@]}" "$HOST" 'bash -lc "echo \$BLACKHOLE"' 2>/dev/null | tail -1)
[ -n "$STORE" ] || { echo "Could not read \$BLACKHOLE on $HOST" >&2; exit 1; }
DEST="$STORE/makai/hf/lerobot/local"      # where the jobs look for datasets (namespace `local`)
"${SSH[@]}" "$HOST" "mkdir -p $DEST"
rsync -az --delete --progress -e "${SSH[*]}" "$SRC/" "$HOST:$DEST/makai_$1/"
echo "Sent. On the cluster:  scripts/hpc/submit.sh $1 <run name> STEPS=100000"
