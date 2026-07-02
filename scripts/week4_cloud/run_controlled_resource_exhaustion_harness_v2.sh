#!/usr/bin/env bash
# Week4：隔离的确定性 HTTP 500 CUDA-OOM fault injection。
# 运行期文件全部落到 /opt；验证 Redis shared breaker：
# fault primary -> fallback -> breaker open -> 新 Gateway + success primary recovery。
# 不等同于真实 GPU/KV Cache OOM。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/opt/venvs/week4-gateway/bin/python}"

REDIS_PORT="${REDIS_PORT:-16380}"
FAULT_PRIMARY_PORT="${FAULT_PRIMARY_PORT:-18111}"
FALLBACK_PORT="${FALLBACK_PORT:-18112}"
SUCCESS_PRIMARY_PORT="${SUCCESS_PRIMARY_PORT:-18113}"
FAULT_GATEWAY_PORT="${FAULT_GATEWAY_PORT:-18080}"
RECOVERY_GATEWAY_PORT="${RECOVERY_GATEWAY_PORT:-18081}"

RECOVERY_TIMEOUT_SECONDS="${RECOVERY_TIMEOUT_SECONDS:-2}"
RUN_TAG="${RUN_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}"
RUN_DIR="${RUN_DIR:-/opt/week4-resource-exhaustion/${RUN_TAG}_shared_breaker_v2}"
ARCHIVE_DIR="${ARCHIVE_DIR:-$REPO_ROOT/evidence/week4_resource_exhaustion/${RUN_TAG}_shared_breaker_v2}"
KEY_PREFIX="${KEY_PREFIX:-week4:resource-exhaustion-v2:${RUN_TAG}}"

mkdir -p "$RUN_DIR"/{logs,snapshots,redis}

PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill -TERM "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT

ensure_free() {
  local port="$1"
  if ss -ltn | awk '{print $4}' | grep -qx "127.0.0.1:${port}"; then
    echo "port_in_use=${port}" >&2
    exit 40
  fi
}

wait_http() {
  local url="$1"
  local name="$2"

  for _ in $(seq 1 60); do
    if "$PYTHON_BIN" - "$url" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
    raise SystemExit(0 if 200 <= response.status < 300 else 1)
PY
    then
      echo "ready=${name} url=${url}"
      return 0
    fi
    sleep 0.5
  done

  echo "not_ready=${name} url=${url}" >&2
  return 1
}

start_mock() {
  local port="$1"
  local mode="$2"
  local name="$3"
  local log="$4"

  PYTHONDONTWRITEBYTECODE=1 \
    "$PYTHON_BIN" "$REPO_ROOT/scripts/week4_cloud/mock_openai_fault_server.py" \
      --port "$port" \
      --mode "$mode" \
      --model-name "$name" \
      >"$log" 2>&1 &

  PIDS+=("$!")
}

start_gateway() {
  local port="$1"
  local primary_port="$2"
  local primary_model="$3"
  local log="$4"

  (
    cd "$REPO_ROOT"
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$REPO_ROOT" \
    INFERENCE_BACKEND=vllm \
    VLLM_BASE_URL="http://127.0.0.1:${primary_port}/v1" \
    VLLM_MODEL_NAME="$primary_model" \
    VLLM_TIMEOUT_SECONDS=10 \
    VLLM_FALLBACK_BASE_URL="http://127.0.0.1:${FALLBACK_PORT}/v1" \
    VLLM_FALLBACK_MODEL_NAME="Seed-OSS-fallback-controlled" \
    VLLM_FALLBACK_TIMEOUT_SECONDS=10 \
    VLLM_ENABLE_SEED_THINKING_BUDGET=true \
    RESILIENCE_STATE_STORE=redis \
    RESILIENCE_REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/0" \
    RESILIENCE_REDIS_KEY_PREFIX="$KEY_PREFIX" \
    RESILIENCE_FAILURE_THRESHOLD=1 \
    RESILIENCE_RETRY_ATTEMPTS=1 \
    RESILIENCE_RETRY_BACKOFF_SECONDS=0 \
    RESILIENCE_RECOVERY_TIMEOUT_SECONDS="$RECOVERY_TIMEOUT_SECONDS" \
    RESILIENCE_REDIS_PROBE_LEASE_MS=30000 \
    FASTAPI_PORT="$port" \
    PATH="/opt/venvs/week4-gateway/bin:$PATH" \
      bash deployment/cloud/run_week4_gateway.sh
  ) >"$log" 2>&1 &

  PIDS+=("$!")
}

request_gateway() {
  local phase="$1"
  local port="$2"

  "$PYTHON_BIN" - "$phase" "$port" "$RUN_DIR" <<'PY'
import json
import sys
import urllib.request
from pathlib import Path

phase, port, run_dir = sys.argv[1:]
payload = {
    "prompt": "受控 CUDA OOM 故障注入验证。",
    "max_new_tokens": 8,
    "temperature": 0.0,
    "thinking_budget": 512,
}

request = urllib.request.Request(
    f"http://127.0.0.1:{port}/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(request, timeout=30) as response:
    record = {
        "phase": phase,
        "http_status": response.status,
        "payload": json.loads(response.read().decode("utf-8")),
    }

path = Path(run_dir) / phase / "gateway_response.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(record, ensure_ascii=False))
PY
}

snapshot() {
  local phase="$1"
  local dir="$RUN_DIR/$phase"
  mkdir -p "$dir"

  curl -fsS "http://127.0.0.1:${FAULT_GATEWAY_PORT}/metrics" \
    >"$dir/fault_gateway_metrics.txt" 2>&1 || true

  curl -fsS "http://127.0.0.1:${RECOVERY_GATEWAY_PORT}/metrics" \
    >"$dir/recovery_gateway_metrics.txt" 2>&1 || true

  redis-cli -p "$REDIS_PORT" --raw HGETALL "{${KEY_PREFIX}}:circuit" \
    >"$dir/redis_circuit_state.txt" 2>&1 || true

  nvidia-smi --query-gpu=index,memory.used,utilization.gpu \
    --format=csv,noheader \
    >"$dir/gpu_snapshot.txt" 2>&1 || true
}

validate() {
  "$PYTHON_BIN" - "$RUN_DIR" <<'PY'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])

expected = {
    "resource_exhausted_fallback": ("fallback", 1, 512),
    "breaker_open_fallback": ("fallback", 0, 512),
    "primary_recovered_cross_gateway": ("primary", 1, None),
}

errors = []
results = {}

for phase, wanted in expected.items():
    body = json.loads(
        (run_dir / phase / "gateway_response.json").read_text()
    )["payload"]
    actual = (
        body.get("route"),
        body.get("primary_attempts"),
        body.get("fallback_thinking_budget"),
    )
    results[phase] = {"expected": wanted, "actual": actual}
    if actual != wanted:
        errors.append(f"{phase}: expected={wanted}, actual={actual}")

result = {
    "validation_passed": not errors,
    "errors": errors,
    "phases": results,
    "boundary": (
        "确定性 HTTP 500 CUDA-OOM fault injection；验证错误分类、"
        "Redis shared breaker、fallback 与跨Gateway recovery；"
        "不等同于真实 GPU 或 KV Cache OOM。"
    ),
}

(run_dir / "harness_validation.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
PY
}

for port in \
  "$REDIS_PORT" \
  "$FAULT_PRIMARY_PORT" \
  "$FALLBACK_PORT" \
  "$SUCCESS_PRIMARY_PORT" \
  "$FAULT_GATEWAY_PORT" \
  "$RECOVERY_GATEWAY_PORT"
do
  ensure_free "$port"
done

redis-server \
  --port "$REDIS_PORT" \
  --bind 127.0.0.1 \
  --dir "$RUN_DIR/redis" \
  --save "" \
  --appendonly no \
  >"$RUN_DIR/logs/redis.log" 2>&1 &
PIDS+=("$!")

for _ in $(seq 1 40); do
  redis-cli -p "$REDIS_PORT" ping >/dev/null 2>&1 && break
  sleep 0.5
done
redis-cli -p "$REDIS_PORT" ping >/dev/null

start_mock \
  "$FAULT_PRIMARY_PORT" \
  resource-exhausted \
  Seed-OSS-primary-controlled \
  "$RUN_DIR/logs/fault_primary.log"

start_mock \
  "$FALLBACK_PORT" \
  success \
  Seed-OSS-fallback-controlled \
  "$RUN_DIR/logs/fallback.log"

wait_http "http://127.0.0.1:${FAULT_PRIMARY_PORT}/v1/models" fault_primary
wait_http "http://127.0.0.1:${FALLBACK_PORT}/v1/models" fallback

start_gateway \
  "$FAULT_GATEWAY_PORT" \
  "$FAULT_PRIMARY_PORT" \
  Seed-OSS-primary-controlled \
  "$RUN_DIR/logs/fault_gateway.log"

wait_http "http://127.0.0.1:${FAULT_GATEWAY_PORT}/health" fault_gateway

request_gateway resource_exhausted_fallback "$FAULT_GATEWAY_PORT"
snapshot resource_exhausted_fallback

request_gateway breaker_open_fallback "$FAULT_GATEWAY_PORT"
snapshot breaker_open_fallback

start_mock \
  "$SUCCESS_PRIMARY_PORT" \
  success \
  Seed-OSS-primary-recovered-controlled \
  "$RUN_DIR/logs/success_primary.log"

wait_http "http://127.0.0.1:${SUCCESS_PRIMARY_PORT}/v1/models" success_primary

start_gateway \
  "$RECOVERY_GATEWAY_PORT" \
  "$SUCCESS_PRIMARY_PORT" \
  Seed-OSS-primary-recovered-controlled \
  "$RUN_DIR/logs/recovery_gateway.log"

wait_http "http://127.0.0.1:${RECOVERY_GATEWAY_PORT}/health" recovery_gateway

sleep "$((RECOVERY_TIMEOUT_SECONDS + 1))"

request_gateway primary_recovered_cross_gateway "$RECOVERY_GATEWAY_PORT"
snapshot primary_recovered_cross_gateway

validate

echo "RUN_DIR=$RUN_DIR"
echo "ARCHIVE_DIR=$ARCHIVE_DIR"
echo "RESOURCE_EXHAUSTION_HARNESS_V2_PASSED=1"
