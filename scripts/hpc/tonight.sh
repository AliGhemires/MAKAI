#!/usr/bin/env bash
# From the laptop that has access to the DTU HPC cluster: send the recorded datasets and
# launch the night's trainings, in priority order. One command, safe to run again.
#
#   scripts/hpc/tonight.sh
#
# It looks for pick_sock_v1 and pick_can_v1 on this laptop, in
#   ~/.cache/huggingface/lerobot/local/makai_<name>/      (or under your Hub namespace)
# If a teammate recorded them, just drop the zips he sent (makai_pick_sock_v1.zip, ...) in
# ~/Downloads or on the Desktop: they are unpacked for you.
# A dataset that is missing is skipped, with its runs.
#
# Runs submitted (docs/TRAINING.md says why): reference sock and can (100000 steps), their
# lighting-augmented variants, sock with a short horizon, sock with the wrist camera only.
# Follow them with:  ssh dtu bstat      Fetch a model with:  scripts/hpc/fetch_model.sh <run>
#
# To see what it would do without touching the cluster:  DRY_RUN=1 scripts/hpc/tonight.sh
# For a real rehearsal (it DOES submit jobs):  SOCK=<dataset> CAN=<dataset> SUFFIX=_test \
#     STEPS_REF=200 STEPS_VAR=200 BSUB="-W 0:15" scripts/hpc/tonight.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
HOST="${HPC_HOST:-dtu}"
SOCK="${SOCK:-pick_sock_v1}"; CAN="${CAN:-pick_can_v1}"; SUFFIX="${SUFFIX:-}"
REF="${STEPS_REF:-100000}"; VAR="${STEPS_VAR:-40000}"; BSUB="${BSUB:-}"
# The shared connection ~/.ssh/cm-<host> answers whatever host name ssh is given: only use it
# for the host it was opened for.
SSH=(ssh); [ -S "$HOME/.ssh/cm-$HOST" ] && SSH=(ssh -o "ControlPath=$HOME/.ssh/cm-$HOST")
NS="${HUB_NAMESPACE:-$(uv run --no-sync python -c "from makai.config import load_config; print(load_config()['hub']['namespace'])")}"
[ "$NS" = "CHANGE_ME" ] && NS=local
DATA="${HF_LEROBOT_HOME:-$HOME/.cache/huggingface/lerobot}/${NS}"
have() { [ -d "$DATA/makai_$1" ]; }

# A teammate recorded them? Unpack the zips he sent (scripts/collect.py makes them) when they
# are newer than what is here.
for name in "$SOCK" "$CAN"; do
  for zip in "$HOME/Downloads/makai_$name.zip" "$HOME/Desktop/makai_$name.zip"; do
    if [ -f "$zip" ] && { ! have "$name" || [ "$zip" -nt "$DATA/makai_$name" ]; }; then
      mkdir -p "$DATA" && rm -rf "$DATA/makai_$name" && unzip -q -o "$zip" -d "$DATA" && echo "unpacked $zip"
    fi
  done
done

have "$SOCK" || have "$CAN" || { echo "No dataset found in $DATA (looked for makai_$SOCK and makai_$CAN)." >&2; exit 1; }
if [ "${DRY_RUN:-0}" = "1" ]; then   # say what would happen, touch nothing on the cluster
  for name in "$SOCK" "$CAN"; do have "$name" && echo "would send $name ($(du -sh "$DATA/makai_$name" | cut -f1))" || echo "would skip $name (not on this laptop)"; done
  echo "would submit to $HOST: reference runs at $REF steps, variants at $VAR steps"
  exit 0
fi
"${SSH[@]}" "$HOST" true || { echo "Cannot reach $HOST: open the shared connection first (scripts/hpc/push_dataset.sh says how)." >&2; exit 1; }

echo "== 1/3 sending the datasets"
for name in "$SOCK" "$CAN"; do
  if have "$name"; then scripts/hpc/push_dataset.sh "$name" | tail -1; else echo "skipped: $name is not on this laptop"; fi
done
if have "$SOCK"; then
  scripts/wrist_only.sh "$SOCK" > /dev/null 2>&1 && scripts/hpc/push_dataset.sh "${SOCK}_wrist" | tail -1
fi

echo "== 2/3 updating the code on the cluster"
rsync -az --delete -e "${SSH[*]}" --exclude .venv --exclude outputs --exclude data --exclude .git \
  --include 'models/detector_*.pt' --exclude '*.pt' --exclude __pycache__ --exclude '.*_cache' \
  --exclude 'mobileclip*' --exclude 'makai_act_*' ./ "$HOST:MAKAI/"

echo "== 3/3 submitting the trainings"
JOBS=""
add() { JOBS+="scripts/hpc/submit.sh $* $BSUB 2>&1 | tail -1; "; }
have "$SOCK" && add "$SOCK" "act_sock_v1$SUFFIX" "STEPS=$REF"
have "$CAN"  && add "$CAN"  "act_can_v1$SUFFIX"  "STEPS=$REF"
have "$SOCK" && add "$SOCK" "act_sock_v1_aug$SUFFIX" "STEPS=$VAR" AUGMENT=1
have "$CAN"  && add "$CAN"  "act_can_v1_aug$SUFFIX"  "STEPS=$VAR" AUGMENT=1
have "$SOCK" && add "$SOCK" "act_sock_v1_c50$SUFFIX" "STEPS=$VAR" "EXTRA='--policy.chunk_size=50 --policy.n_action_steps=50'"
have "$SOCK" && add "${SOCK}_wrist" "act_sock_v1_wrist$SUFFIX" "STEPS=$VAR"
"${SSH[@]}" "$HOST" "bash -lc \"cd ~/MAKAI && $JOBS sleep 20; bjobs 2>/dev/null | cut -c1-90\"" 2>/dev/null
echo
echo "Submitted. PEND = waiting for a GPU, RUN = training. Check again with:  ${SSH[*]} $HOST bstat"
