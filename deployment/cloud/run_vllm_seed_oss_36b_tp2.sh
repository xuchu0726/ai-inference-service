#!/usr/bin/env bash
set -euo pipefail

# Cloud vLLM Seed-OSS-36B tensor-parallel server template.
# Purpose:
#   Start Seed-OSS-36B with vLLM on a multi-GPU cloud instance.
#   This script is for short-context smoke test first, then benchmark.
#
# Notes:
#   1. This script assumes the cloud instance has enough GPU memory.
#   2. Start with a conservative max_model_len to reduce KV Cache pressure.
#   3. Increase context length only after short-context serving works.
#   4. If model access requires authentication, run `huggingface-cli login`
#      or configure HF_TOKEN before executing this script.

MODEL_NAME="${MODEL_NAME:-ByteDance-Seed/Seed-OSS-36B}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8001}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-2}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
DTYPE="${DTYPE:-bfloat16}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"

mkdir -p logs results

echo "===== CLOUD VLLM SEED-OSS-36B TP SERVER ====="
echo "MODEL_NAME=${MODEL_NAME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE}"
echo "MAX_MODEL_LEN=${MAX_MODEL_LEN}"
echo "GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION}"
echo "DTYPE=${DTYPE}"
echo "HF_HOME=${HF_HOME}"

echo
echo "===== NVIDIA SMI ====="
nvidia-smi || true

echo
echo "===== PYTHON / GPU CHECK ====="
python - <<'PY'
import sys
print("python:", sys.version)

try:
    import torch
    print("torch:", torch.__version__)
    print("torch cuda:", torch.version.cuda)
    print("cuda available:", torch.cuda.is_available())
    print("device count:", torch.cuda.device_count())
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            print(f"device {i}:", torch.cuda.get_device_name(i))
except Exception as exc:
    print("torch check failed:", repr(exc))

try:
    import vllm
    print("vllm:", vllm.__version__)
except Exception as exc:
    print("vllm check failed:", repr(exc))
PY

echo
echo "===== START VLLM SEED-OSS-36B SERVER ====="
python -m vllm.entrypoints.openai.api_server \
  --host "${HOST}" \
  --port "${PORT}" \
  --model "${MODEL_NAME}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --dtype "${DTYPE}" \
  --enable-prefix-caching
