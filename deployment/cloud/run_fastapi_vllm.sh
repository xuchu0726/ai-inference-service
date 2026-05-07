#!/usr/bin/env bash
set -euo pipefail

# Start project FastAPI server and connect it to a running vLLM server.

export INFERENCE_BACKEND="${INFERENCE_BACKEND:-vllm}"
export MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-1.5B-Instruct}"
export VLLM_MODEL_NAME="${VLLM_MODEL_NAME:-$MODEL_NAME}"
export VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8001/v1}"
export VLLM_TIMEOUT_SECONDS="${VLLM_TIMEOUT_SECONDS:-300}"

HOST="${FASTAPI_HOST:-0.0.0.0}"
PORT="${FASTAPI_PORT:-8000}"

mkdir -p logs results

echo "===== START FASTAPI WITH VLLM BACKEND ====="
echo "INFERENCE_BACKEND=${INFERENCE_BACKEND}"
echo "MODEL_NAME=${MODEL_NAME}"
echo "VLLM_MODEL_NAME=${VLLM_MODEL_NAME}"
echo "VLLM_BASE_URL=${VLLM_BASE_URL}"
echo "HOST=${HOST}"
echo "PORT=${PORT}"

python -m uvicorn app.main:app --host "${HOST}" --port "${PORT}"
