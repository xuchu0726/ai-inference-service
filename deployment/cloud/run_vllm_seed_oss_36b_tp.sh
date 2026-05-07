#!/usr/bin/env bash
set -euo pipefail

# Cloud vLLM Seed-OSS-36B-Instruct tensor-parallel server.
#
# Purpose:
#   Start ByteDance-Seed/Seed-OSS-36B-Instruct with vLLM on a multi-GPU cloud instance.
#
# Notes:
#   1. This is the target-model deployment script for Seed-OSS.
#   2. BF16/FP16 deployment requires multi-GPU memory capacity.
#   3. For first smoke test, use shorter context by overriding MAX_MODEL_LEN.
#   4. Qwen baseline scripts are kept separate from this Seed-OSS script.

MODEL_NAME="${MODEL_NAME:-ByteDance-Seed/Seed-OSS-36B-Instruct}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8001}"

# Full deployment should use enough GPUs for tensor parallelism.
# For short-context smoke tests on limited resources, override explicitly:
#   TENSOR_PARALLEL_SIZE=2 MAX_MODEL_LEN=4096 bash deployment/cloud/run_vllm_seed_oss_36b_tp.sh
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-8}"

# Seed-OSS supports long context, but first smoke test should use 4096 / 8192 / 16384.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-65536}"

GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.95}"
DTYPE="${DTYPE:-bfloat16}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-32768}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"

mkdir -p logs results

echo "===== CLOUD VLLM SEED-OSS-36B-INSTRUCT SERVER ====="
echo "MODEL_NAME=${MODEL_NAME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE}"
echo "MAX_MODEL_LEN=${MAX_MODEL_LEN}"
echo "MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS}"
echo "GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION}"
echo "DTYPE=${DTYPE}"
echo "HF_HOME=${HF_HOME}"

echo
echo "===== NVIDIA SMI ====="
nvidia-smi || true

echo
echo "===== PYTHON / GPU / VLLM CHECK ====="
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
    import transformers
    print("transformers:", transformers.__version__)
except Exception as exc:
    print("transformers check failed:", repr(exc))

try:
    import vllm
    print("vllm:", vllm.__version__)
except Exception as exc:
    print("vllm check failed:", repr(exc))
PY

echo
echo "===== START VLLM SEED-OSS-36B-INSTRUCT SERVER ====="
vllm serve "${MODEL_NAME}" \
  --host "${HOST}" \
  --port "${PORT}" \
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-batched-tokens "${MAX_NUM_BATCHED_TOKENS}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --dtype "${DTYPE}" \
  --enable-auto-tool-choice \
  --tool-call-parser seed_oss \
  --trust-remote-code
