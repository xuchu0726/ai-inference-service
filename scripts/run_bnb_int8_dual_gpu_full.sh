#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="/workspace/venvs/bnb-int8/bin/python"
RUN_DIR="results/week2_hardening/bnb_int8/bnb_int8_full"
LOG_DIR="logs/week2_hardening/bnb_int8/bnb_int8_full"
SHARD_DIR="data/eval/week2_quantization_validation/bnb_int8_full_shards"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$SHARD_DIR"

"$PYTHON_BIN" - <<'PY'
from pathlib import Path

source = Path("data/eval/gsm8k_test.jsonl")
shard_dir = Path("data/eval/gsm8k_bnb_int8_shards")

lines = source.read_text(encoding="utf-8").splitlines()

if len(lines) != 1319:
    raise RuntimeError(f"Expected 1319 GSM8K cases, found {len(lines)}.")

(shard_dir / "gsm8k_0001_0660.jsonl").write_text(
    "\n".join(lines[:660]) + "\n",
    encoding="utf-8",
)
(shard_dir / "gsm8k_0661_1319.jsonl").write_text(
    "\n".join(lines[660:]) + "\n",
    encoding="utf-8",
)

print("Created deterministic GSM8K shards: 660 + 659.")
PY

CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 \
nohup "$PYTHON_BIN" scripts/run_bnb_int8_gsm8k_batched.py \
  --dataset "$SHARD_DIR/gsm8k_0001_0660.jsonl" \
  --output "$RUN_DIR/gsm8k_bnb_int8_gpu0_cases_0001_0660.csv" \
  --summary-output "$RUN_DIR/gsm8k_bnb_int8_gpu0_cases_0001_0660_summary.json" \
  --batch-size 1 \
  --limit 660 \
  --max-new-tokens 256 \
  --thinking-budget 0 \
  > "$LOG_DIR/gsm8k_bnb_int8_gpu0_cases_0001_0660.log" 2>&1 &

GPU0_PID=$!

# Stagger model loading to reduce simultaneous Network Volume read pressure.
sleep 90

CUDA_VISIBLE_DEVICES=1 PYTHONUNBUFFERED=1 \
nohup "$PYTHON_BIN" scripts/run_bnb_int8_gsm8k_batched.py \
  --dataset "$SHARD_DIR/gsm8k_0661_1319.jsonl" \
  --output "$RUN_DIR/gsm8k_bnb_int8_gpu1_cases_0661_1319.csv" \
  --summary-output "$RUN_DIR/gsm8k_bnb_int8_gpu1_cases_0661_1319_summary.json" \
  --batch-size 1 \
  --limit 659 \
  --max-new-tokens 256 \
  --thinking-budget 0 \
  > "$LOG_DIR/gsm8k_bnb_int8_gpu1_cases_0661_1319.log" 2>&1 &

GPU1_PID=$!

cat > "$RUN_DIR/worker_pids_20260619.txt" <<EOF
gpu0_pid=${GPU0_PID}
gpu0_cases=0001-0660
gpu1_pid=${GPU1_PID}
gpu1_cases=0661-1319
batch_size=1
max_new_tokens=256
thinking_budget=0
EOF

echo "Started BnB INT8 full GSM8K evaluation."
echo "GPU0 PID: ${GPU0_PID} | cases: 0001-0660"
echo "GPU1 PID: ${GPU1_PID} | cases: 0661-1319"
