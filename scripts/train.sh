#!/usr/bin/env bash
# Train an ACT policy on one of our datasets, with the team's naming conventions.
#
#   scripts/train.sh <dataset> <run> [extra lerobot-train flags]
#   scripts/train.sh pick_sock_v1 act_pick_v1 --job.target=a10g-large   # Hugging Face Jobs
#   scripts/train.sh pick_sock_v1 act_pick_v1 --policy.device=cuda      # this machine
#
# Env: STEPS (30000), BATCH (16), SAVE_FREQ (5000), HUB_NAMESPACE (default: from configs/).
# See docs/TRAINING.md.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  sed -n '2,9p' "$0"; exit 1
fi
DATASET="$1"; RUN="$2"; shift 2
cd "$(dirname "$0")/.."
NS="${HUB_NAMESPACE:-$(uv run --no-sync python -c "from makai.config import load_config; print(load_config()['hub']['namespace'])")}"
if [ "$NS" = "CHANGE_ME" ]; then
  echo "Set hub.namespace in configs/local.yaml (or HUB_NAMESPACE) first." >&2; exit 1
fi

exec uv run --no-sync lerobot-train \
  --dataset.repo_id="${NS}/makai_${DATASET}" \
  --policy.type=act \
  --policy.repo_id="${NS}/makai_${RUN}" \
  --output_dir="outputs/train/${RUN}" \
  --job_name="${RUN}" \
  --steps="${STEPS:-30000}" \
  --batch_size="${BATCH:-16}" \
  --save_freq="${SAVE_FREQ:-5000}" \
  --save_checkpoint_to_hub=true \
  --trackio.enable=true \
  "$@"
