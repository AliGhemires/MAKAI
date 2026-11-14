#!/usr/bin/env bash
# Train an ACT policy on one of our datasets, with the team's naming conventions.
#
#   scripts/train.sh <dataset> <run> [extra lerobot-train flags]
#
#   scripts/train.sh pick_sock_v1 act_sock_v1 --job.target=a10g-large    # cloud: Hugging Face Jobs
#   scripts/train.sh pick_sock_v1 act_sock_v1 --policy.device=cuda       # this machine, NVIDIA GPU
#   scripts/train.sh pick_sock_v1 act_sock_v1 --policy.device=mps        # this Mac (slow: ~2 s per step)
#
# The dataset is read from this laptop if it is here (~/.cache/huggingface/lerobot/...), from
# the Hub otherwise. Without a Hub namespace (configs/local.yaml) everything stays local.
# On a Mac the run is wrapped in `caffeinate`: otherwise the laptop sleeps and training stops.
#
# Env: STEPS (30000), BATCH (8), SAVE_FREQ (5000), HUB_NAMESPACE, and
# AUGMENT=1: each training image gets a random brightness (x0.5 to x1.5), contrast, saturation
#   and hue, so the policy stops relying on the exact lighting. Colour only: LeRobot's default
#   set also shifts and rotates the image, which would blur where the object is.
# See docs/TRAINING.md and docs/CE_SOIR.md.
set -euo pipefail

if [ "$#" -lt 2 ]; then
  sed -n '2,16p' "$0"; exit 1
fi
DATASET="$1"; RUN="$2"; shift 2
cd "$(dirname "$0")/.."
NS="${HUB_NAMESPACE:-$(uv run --no-sync python -c "from makai.config import load_config; print(load_config()['hub']['namespace'])")}"
PUSH=true
if [ "$NS" = "CHANGE_ME" ] || [ "$NS" = "local" ]; then
  NS=local; PUSH=false
  echo "No Hub namespace set: training from the local dataset, the model stays in ${OUTPUT_ROOT:-outputs/train}/${RUN}."
fi

ARGS=(
  --dataset.repo_id="${NS}/makai_${DATASET}"
  --policy.type=act
  --output_dir="${OUTPUT_ROOT:-outputs/train}/${RUN}"
  --job_name="${RUN}"
  --steps="${STEPS:-30000}"
  --batch_size="${BATCH:-8}"
  --save_freq="${SAVE_FREQ:-5000}"
)
LOCAL_DATA="${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/${NS}/makai_${DATASET}"
if [ -d "$LOCAL_DATA" ]; then
  ARGS+=(--dataset.root="$LOCAL_DATA")
  echo "Dataset: local copy at $LOCAL_DATA"
fi
if [ "$PUSH" = true ]; then
  ARGS+=(--policy.repo_id="${NS}/makai_${RUN}" --save_checkpoint_to_hub=true --trackio.enable=true)
else
  ARGS+=(--policy.push_to_hub=false)
fi
if [ "${AUGMENT:-0}" = "1" ]; then
  LIGHTING='{"brightness": {"weight": 2.0, "type": "ColorJitter", "kwargs": {"brightness": [0.5, 1.5]}}, "contrast": {"weight": 1.0, "type": "ColorJitter", "kwargs": {"contrast": [0.7, 1.3]}}, "saturation": {"weight": 1.0, "type": "ColorJitter", "kwargs": {"saturation": [0.5, 1.5]}}, "hue": {"weight": 1.0, "type": "ColorJitter", "kwargs": {"hue": [-0.05, 0.05]}}}'
  ARGS+=(--dataset.image_transforms.enable=true "--dataset.image_transforms.tfs=${LIGHTING}")
fi

KEEP_AWAKE=()
if command -v caffeinate >/dev/null 2>&1 && [[ "$*" != *"--job.target"* ]]; then
  KEEP_AWAKE=(caffeinate -ims)   # keep the Mac awake for as long as training runs
fi
# No `exec`: a caller (the HPC job) may have cleanup to run when training ends.
# ${X[@]+...}: an empty array is an "unbound variable" for bash older than 4.4 (the cluster's).
${KEEP_AWAKE[@]+"${KEEP_AWAKE[@]}"} uv run --no-sync lerobot-train "${ARGS[@]}" "$@"
