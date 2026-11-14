#!/usr/bin/env bash
# Submit ACT trainings to the DTU HPC cluster. Run it ON the cluster, from the MAKAI folder.
#
# Once:
#   ssh <dtu-user>@login.hpc.dtu.dk
#   curl -LsSf https://astral.sh/uv/install.sh | sh                 # installs ~/.local/bin/uv
#   (from a laptop) rsync -az --exclude .venv --exclude outputs --exclude data --exclude .git \
#                         ./ <host>:MAKAI/                          # the GitHub repo is private
#   cd ~/MAKAI && scripts/hpc/submit.sh --setup                     # builds the environment (10 min)
#   mkdir -p ~/.cache/huggingface && echo <Hugging Face write token> > ~/.cache/huggingface/token
#
# Each training:
#   HUB_NAMESPACE=<namespace> scripts/hpc/submit.sh pick_sock_v1 act_sock_v1 STEPS=100000
#   HUB_NAMESPACE=<namespace> scripts/hpc/submit.sh pick_sock_v1 act_sock_v1_aug STEPS=40000 AUGMENT=1
#   ... pick_sock_v1 act_sock_v1_c50 STEPS=40000 EXTRA="--policy.chunk_size=50 --policy.n_action_steps=50"
#   Extra words that are not VAR=value go to bsub:   ... act_sock_v1 -q gpua100 -W 4:00
#
# The dataset: send it from the laptop with scripts/hpc/push_dataset.sh <dataset> (no Hub
# account needed), or set HUB_NAMESPACE and it is downloaded from the Hub by the job.
#
# Follow a job:  bstat    bpeek <job id>    bkill <job id>
# Results: $BLACKHOLE/makai/outputs/<run>/checkpoints/<step>/pretrained_model  (and on the Hub
# when HUB_NAMESPACE is set). Fetch one from a laptop with rsync, then scripts/try_pick.py.
#
# Everything heavy lives in the scratch folder $BLACKHOLE (the home quota is 30 GB and PyTorch
# alone needs 8). That folder is wiped at the cluster's service windows: copy what you keep.
set -euo pipefail
cd "$(dirname "$0")/../.."
export PATH="$HOME/.local/bin:$PATH"
STORE="${MAKAI_STORE:-${BLACKHOLE:+$BLACKHOLE/makai}}"
if [ -z "$STORE" ]; then
  echo "No scratch folder: \$BLACKHOLE is not set (ask DTU HPC support for one), or set MAKAI_STORE." >&2; exit 1
fi

if [ "${1:-}" = "--setup" ]; then
  mkdir -p "$STORE"
  export UV_CACHE_DIR="$STORE/uv-cache" UV_PROJECT_ENVIRONMENT="$STORE/venv" UV_PYTHON_INSTALL_DIR="$STORE/python"
  uv sync --extra robot --no-dev --frozen
  # The locked PyTorch (CUDA 13 build) no longer runs on the V100 cards, which are the queue
  # that starts within seconds. The CUDA 12.6 build covers every GPU of the cluster.
  uv pip install --python "$STORE/venv/bin/python" "torch==2.14.1+cu126" "torchvision==0.29.1+cu126" \
    --index-url https://download.pytorch.org/whl/cu126
  TORCH_HOME="$STORE/torch" "$STORE/venv/bin/python" -c "import torch, torchvision, lerobot; torchvision.models.resnet18(weights='IMAGENET1K_V1'); print('ready: torch', torch.__version__, '| lerobot', lerobot.__version__, '| GPUs:', torch._C._cuda_getArchFlags())"
  du -sh "$STORE"
  exit 0
fi

if [ "$#" -lt 2 ]; then
  sed -n '2,26p' "$0"; exit 1
fi
DATASET="$1"; RUN="$2"; shift 2
PARAMS=("DATASET=$DATASET" "RUN=$RUN" "HUB_NAMESPACE=${HUB_NAMESPACE:-local}" "MAKAI_STORE=$STORE")
BSUB_ARGS=()
for arg in "$@"; do
  case "$arg" in
    [A-Z_]*=*) PARAMS+=("$arg") ;;
    *) BSUB_ARGS+=("$arg") ;;
  esac
done

EXPORTS=""
for param in "${PARAMS[@]}"; do
  EXPORTS+="export ${param%%=*}=$(printf '%q' "${param#*=}")"$'\n'
done
if [[ " ${PARAMS[*]} " == *" DATA_FROM="* ]]; then   # train from a copy of the dataset already on the cluster
  EXPORTS+='mkdir -p "$MAKAI_STORE/hf/lerobot/$HUB_NAMESPACE" && rsync -a --delete "$DATA_FROM/" "$MAKAI_STORE/hf/lerobot/$HUB_NAMESPACE/makai_$DATASET/"'$'\n'
fi

mkdir -p "$STORE/jobs"
JOB="$STORE/jobs/${RUN}_$(date +%H%M%S).lsf"
# Plain bash, not awk: awk would eat the backslashes that protect spaces in values such as EXTRA.
while IFS= read -r line; do
  if [ "$line" = "#@PARAMETERS@" ]; then printf '%s' "$EXPORTS"; else printf '%s\n' "$line"; fi
done < scripts/hpc/train_act.lsf > "$JOB"
bsub -J "$RUN" ${BSUB_ARGS[@]+"${BSUB_ARGS[@]}"} < "$JOB"
