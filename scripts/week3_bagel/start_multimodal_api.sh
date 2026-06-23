#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${BAGEL_GATEWAY_PY:-/workspace/venvs/week3-bagel-gateway/bin/python}"
LOG_FILE="$ROOT_DIR/logs/week3_bagel/multimodal_api.log"
PID_FILE="$ROOT_DIR/logs/week3_bagel/multimodal_api.pid"

if ss -ltn | grep -q ':8000 '; then
  echo "port 8000 is already in use; refusing to replace an existing service"
  exit 1
fi

nohup env \
  PYTHONPATH="$ROOT_DIR" \
  BAGEL_BASE_URL="http://127.0.0.1:7860" \
  BAGEL_TIMEOUT_SECONDS="120" \
  "$PYTHON_BIN" -m uvicorn app.multimodal.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  > "$LOG_FILE" 2>&1 < /dev/null &

echo $! > "$PID_FILE"
echo "pid=$(cat "$PID_FILE")"
