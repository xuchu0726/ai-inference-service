#!/usr/bin/env bash
set -euo pipefail

# Cloud vLLM smoke-test server.
# Purpose:
#   Start a small Qwen2.5 model with vLLM on a cloud GPU instance.
#   This validates CUDA, vLLM, model download, OpenAI-compatible serving,
#   and provides a baseline before switching to Seed-OSS-36B.

MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-1.5B-Instruct}"
HOST="${VLLM_HOST:-0.0.0.0}"
PORT="${VLLM_PORT:-8001}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.85}"

export CUDA_DEVICE_ORDER=PCI_BUS_ID
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
export TRANSFORMERS_CACHE="${TRANSFORMERS_CACHE:-$HF_HOME/transformers}"

mkdir -p logs results

echo "===== CLOUD VLLM QWEN 1.5B SERVER ====="
echo "MODEL_NAME=${MODEL_NAME}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"
echo "MAX_MODEL_LEN=${MAX_MODEL_LEN}"
echo "GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION}"
echo "HF_HOME=${HF_HOME}"

echo
echo "===== NVIDIA SMI ====="
nvidia-smi || true

echo
echo "===== PYTHON / VLLM CHECK ====="
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
echo "===== START VLLM SERVER ====="
python -m vllm.entrypoints.openai.api_server \
  --host "${HOST}" \
  --port "${PORT}" \
  --model "${MODEL_NAME}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --enable-prefix-caching
