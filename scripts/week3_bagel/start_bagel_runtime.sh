#!/usr/bin/env bash
set -euo pipefail

LOG_DIR="/workspace/ai-inference-service/logs/week3_bagel"
LOG_FILE="$LOG_DIR/bagel_runtime.log"
PID_FILE="$LOG_DIR/bagel_runtime.pid"

if ss -ltn | grep -q ':7860 '; then
  echo "port 7860 is already in use; refusing to replace an existing BAGEL runtime"
  exit 1
fi

mkdir -p "$LOG_DIR"
cd "/workspace/bagel_week3"

nohup /workspace/bagel_week3/venv/bin/python /workspace/bagel_week3/vendor/BAGEL/app.py --server_name 0.0.0.0 --server_port 7860 --model_path /workspace/bagel_week3/models/BAGEL-7B-MoT > "$LOG_FILE" 2>&1 < /dev/null &
echo $! > "$PID_FILE"
echo "pid=$(cat "$PID_FILE")"
