#!/usr/bin/env bash
set -euo pipefail

# Week4：单个 Seed-OSS-36B W8A8 TP=2 vLLM 实例。
# 调用方必须显式指定 CUDA_VISIBLE_DEVICES、VLLM_PORT、SERVED_MODEL_NAME。
# 两个实例分别占用 GPU 0,1 与 GPU 2,3，用作 primary / fallback。

MODEL_PATH="${MODEL_PATH:?MODEL_PATH is required}"
CUDA_DEVICE_SET="${CUDA_VISIBLE_DEVICES:?CUDA_VISIBLE_DEVICES is required}"
VLLM_PORT="${VLLM_PORT:?VLLM_PORT is required}"
SERVED_MODEL_NAME="${SERVED_MODEL_NAME:?SERVED_MODEL_NAME is required}"

TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-2}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-8192}"
MAX_NUM_SEQS="${MAX_NUM_SEQS:-16}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.90}"
DTYPE="${DTYPE:-bfloat16}"

export CUDA_VISIBLE_DEVICES="$CUDA_DEVICE_SET"
export CUDA_DEVICE_ORDER=PCI_BUS_ID

echo "===== Week4 Seed W8A8 TP=2 instance ====="
echo "CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"
echo "MODEL_PATH=$MODEL_PATH"
echo "VLLM_PORT=$VLLM_PORT"
echo "SERVED_MODEL_NAME=$SERVED_MODEL_NAME"
echo "TENSOR_PARALLEL_SIZE=$TENSOR_PARALLEL_SIZE"
echo "MAX_MODEL_LEN=$MAX_MODEL_LEN"
echo "MAX_NUM_BATCHED_TOKENS=$MAX_NUM_BATCHED_TOKENS"
echo "MAX_NUM_SEQS=$MAX_NUM_SEQS"
echo "GPU_MEMORY_UTILIZATION=$GPU_MEMORY_UTILIZATION"

exec vllm serve "$MODEL_PATH" \
  --served-model-name "$SERVED_MODEL_NAME" \
  --host 0.0.0.0 \
  --port "$VLLM_PORT" \
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE" \
  --dtype "$DTYPE" \
  --quantization compressed-tensors \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS" \
  --max-num-seqs "$MAX_NUM_SEQS" \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --trust-remote-code \
  --enforce-eager \
  --safetensors-load-strategy prefetch
