#!/usr/bin/env bash
set -euo pipefail

# Experimental low-resource Seed-OSS-36B-Instruct TP=2 smoke-test wrapper.
# This is not the official recommended full deployment configuration.
# Use only for short-context feasibility checks.

export TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-2}"
export MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
export MAX_NUM_BATCHED_TOKENS="${MAX_NUM_BATCHED_TOKENS:-8192}"

bash "$(dirname "$0")/run_vllm_seed_oss_36b_tp.sh"
