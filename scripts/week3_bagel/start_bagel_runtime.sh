#!/usr/bin/env bash
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

BAGEL_ROOT="${BAGEL_ROOT:-/workspace/bagel_week3}"
BAGEL_PYTHON="${BAGEL_PYTHON:-$BAGEL_ROOT/venv/bin/python}"
BAGEL_APP="${BAGEL_APP:-$BAGEL_ROOT/vendor/BAGEL/app.py}"
BAGEL_MODEL_PATH="${BAGEL_MODEL_PATH:-$BAGEL_ROOT/models/BAGEL-7B-MoT}"
BAGEL_PORT="${BAGEL_PORT:-7860}"

LOG_DIR="${BAGEL_LOG_DIR:-$REPO_ROOT/logs/week3_bagel}"
LOG_FILE="$LOG_DIR/bagel_runtime.log"
PID_FILE="$LOG_DIR/bagel_runtime.pid"

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

if port_is_in_use "$BAGEL_PORT"; then
  echo "port ${BAGEL_PORT} is already in use; refusing to replace an existing BAGEL runtime"
  exit 3
fi

for path in "$BAGEL_PYTHON" "$BAGEL_APP" "$BAGEL_MODEL_PATH"; do
  if [ ! -e "$path" ]; then
    echo "required BAGEL asset missing: $path"
    exit 4
  fi
done

mkdir -p "$LOG_DIR"

nohup "$BAGEL_PYTHON" "$BAGEL_APP" \
  --server_name 0.0.0.0 \
  --server_port "$BAGEL_PORT" \
  --model_path "$BAGEL_MODEL_PATH" \
  > "$LOG_FILE" 2>&1 < /dev/null &

echo $! > "$PID_FILE"

echo "pid=$(cat "$PID_FILE")"
echo "port=$BAGEL_PORT"
echo "model_path=$BAGEL_MODEL_PATH"
echo "log_file=$LOG_FILE"
