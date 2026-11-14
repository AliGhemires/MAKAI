#!/usr/bin/env bash
# Make a copy of a dataset that keeps only the wrist camera, to train a policy that does not
# look at the room (the front camera sees walls, people and a floor that will be different
# in the demo room; the wrist camera sees little more than the object and the gripper).
#
#   scripts/wrist_only.sh pick_sock_v1          ->  dataset pick_sock_v1_wrist
#   scripts/train.sh pick_sock_v1_wrist act_sock_v1_wrist ...
#
# The dataset must be on this laptop (it is, right after recording). The copy is pushed to
# the Hub when a namespace is set, so it can be trained anywhere. The robot code needs no
# change: a wrist-only model simply ignores the front image.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  sed -n '2,11p' "$0"; exit 1
fi
DATASET="$1"
cd "$(dirname "$0")/.."
NS="${HUB_NAMESPACE:-$(uv run --no-sync python -c "from makai.config import load_config; print(load_config()['hub']['namespace'])")}"
PUSH=true
if [ "$NS" = "CHANGE_ME" ]; then NS=local; PUSH=false; fi
HOME_DIR="${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}"
SRC="${HOME_DIR}/${NS}/makai_${DATASET}"
DST="${HOME_DIR}/${NS}/makai_${DATASET}_wrist"
if [ ! -d "$SRC" ]; then
  echo "Dataset not found on this laptop: $SRC" >&2; exit 1
fi
rm -rf "$DST"   # always rebuilt from the current dataset, so added episodes are included
uv run --no-sync lerobot-edit-dataset \
  --repo_id "${NS}/makai_${DATASET}" --root "$SRC" \
  --new_repo_id "${NS}/makai_${DATASET}_wrist" --new_root "$DST" \
  --operation.type remove_feature --operation.feature_names "['observation.images.front']" \
  --push_to_hub "$PUSH"
echo "Wrist-only copy: ${NS}/makai_${DATASET}_wrist"
