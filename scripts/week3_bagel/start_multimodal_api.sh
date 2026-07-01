#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

BAGEL_GATEWAY_PY="${BAGEL_GATEWAY_PY:-/workspace/venvs/week3-bagel-gateway/bin/python}"
BAGEL_BASE_URL="${BAGEL_BASE_URL:-http://127.0.0.1:7860}"
BAGEL_TIMEOUT_SECONDS="${BAGEL_TIMEOUT_SECONDS:-120}"
BAGEL_GATEWAY_PORT="${BAGEL_GATEWAY_PORT:-8000}"

LOG_DIR="${BAGEL_GATEWAY_LOG_DIR:-$ROOT_DIR/logs/week3_bagel}"
LOG_FILE="$LOG_DIR/multimodal_api.log"
PID_FILE="$LOG_DIR/multimodal_api.pid"

port_is_in_use() {
  local port="$1"
  python - "$port" <<'PYPORT'
import socket
import sys

port = int(sys.argv[1])
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.bind(("0.0.0.0", port))
except OSError:
    raise SystemExit(0)
finally:
    sock.close()
raise SystemExit(1)
PYPORT
}

if [ ! -x "$BAGEL_GATEWAY_PY" ]; then
  echo "BAGEL gateway Python is unavailable: $BAGEL_GATEWAY_PY"
  exit 3
fi

if port_is_in_use "$BAGEL_GATEWAY_PORT"; then
  echo "port ${BAGEL_GATEWAY_PORT} is already in use; refusing to replace an existing service"
  exit 4
fi

mkdir -p "$LOG_DIR"

nohup env \
  PYTHONPATH="$ROOT_DIR" \
  BAGEL_BASE_URL="$BAGEL_BASE_URL" \
  BAGEL_TIMEOUT_SECONDS="$BAGEL_TIMEOUT_SECONDS" \
  "$BAGEL_GATEWAY_PY" -m uvicorn app.multimodal.main:app \
  --host 0.0.0.0 \
  --port "$BAGEL_GATEWAY_PORT" \
  > "$LOG_FILE" 2>&1 < /dev/null &

echo $! > "$PID_FILE"

echo "pid=$(cat "$PID_FILE")"
echo "port=$BAGEL_GATEWAY_PORT"
echo "base_url=$BAGEL_BASE_URL"
echo "log_file=$LOG_FILE"
