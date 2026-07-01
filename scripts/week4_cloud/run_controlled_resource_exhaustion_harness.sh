#!/usr/bin/env bash
# Week4：确定性 HTTP 500 CUDA-OOM fault injection。
# 验证：资源耗尽分类 -> Redis breaker -> low-budget fallback -> primary recovery。
# 不等同于真实 GPU OOM；真实 GPU/KV Cache 压力实验在云端执行。

set -u
set -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python}"
REDIS_PORT="${REDIS_PORT:-16379}"
PRIMARY_PORT="${PRIMARY_PORT:-18101}"
FALLBACK_PORT="${FALLBACK_PORT:-18102}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
RECOVERY_TIMEOUT_SECONDS="${RECOVERY_TIMEOUT_SECONDS:-2}"
RUN_TAG="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_DIR="${RUN_DIR:-evidence/week4_resource_exhaustion/$RUN_TAG}"

mkdir -p "$RUN_DIR"

REDIS_PID=""
REDIS_DOCKER_NAME=""
PRIMARY_PID=""
FALLBACK_PID=""
GATEWAY_PID=""

cleanup() {
  for pid in "$GATEWAY_PID" "$PRIMARY_PID" "$FALLBACK_PID" "$REDIS_PID"; do
    if [ -n "${pid:-}" ]; then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done

  if [ -n "${REDIS_DOCKER_NAME:-}" ]; then
    docker rm -f "$REDIS_DOCKER_NAME" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_http() {
  local url="$1"
  local name="$2"

  for _ in $(seq 1 60); do
    if "$PYTHON_BIN" - "$url" <<'PY_HTTP' >/dev/null 2>&1
import sys
import urllib.request

with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
    raise SystemExit(0 if 200 <= response.status < 300 else 1)
PY_HTTP
    then
      echo "ready=$name url=$url"
      return 0
    fi
    sleep 0.5
  done

  echo "not_ready=$name url=$url" >&2
  return 1
}

wait_redis() {
  for _ in $(seq 1 40); do
    if "$PYTHON_BIN" -c '
import sys
import redis

client = redis.Redis(
    host="127.0.0.1",
    port=int(sys.argv[1]),
    db=0,
    socket_connect_timeout=1,
    socket_timeout=1,
)
raise SystemExit(0 if client.ping() else 1)
' "$REDIS_PORT" >/dev/null 2>&1; then
      echo "ready=redis port=$REDIS_PORT"
      return 0
    fi
    sleep 0.5
  done

  echo "not_ready=redis port=$REDIS_PORT" >&2
  return 1
}

start_redis() {
  if command -v redis-server >/dev/null 2>&1; then
    redis-server \
      --port "$REDIS_PORT" \
      --save "" \
      --appendonly no \
      --bind 127.0.0.1 \
      > "$RUN_DIR/redis.log" 2>&1 &
    REDIS_PID=$!
    echo "redis_mode=local_process" | tee "$RUN_DIR/redis_mode.txt"
    return 0
  fi

  if ! command -v docker >/dev/null 2>&1; then
    echo "Neither redis-server nor docker is available." >&2
    return 20
  fi

  REDIS_DOCKER_NAME="week4-resource-redis-${RUN_TAG}"
  docker rm -f "$REDIS_DOCKER_NAME" >/dev/null 2>&1 || true

  if ! docker run -d \
    --name "$REDIS_DOCKER_NAME" \
    -p "127.0.0.1:${REDIS_PORT}:6379" \
    redis:7-alpine \
    > "$RUN_DIR/redis_docker_id.txt"; then
    echo "Failed to start Docker Redis container." >&2
    return 21
  fi

  echo "redis_mode=docker_container" | tee "$RUN_DIR/redis_mode.txt"
}

start_primary() {
  local mode="$1"

  "$PYTHON_BIN" scripts/week4_cloud/mock_openai_fault_server.py \
    --port "$PRIMARY_PORT" \
    --mode "$mode" \
    --model-name "Seed-OSS-primary-controlled" \
    > "$RUN_DIR/primary_${mode}.log" 2>&1 &

  PRIMARY_PID=$!
}

start_fallback() {
  "$PYTHON_BIN" scripts/week4_cloud/mock_openai_fault_server.py \
    --port "$FALLBACK_PORT" \
    --mode success \
    --model-name "Seed-OSS-fallback-controlled" \
    > "$RUN_DIR/fallback.log" 2>&1 &

  FALLBACK_PID=$!
}

snapshot_phase() {
  local phase="$1"
  local phase_dir="$RUN_DIR/$phase"
  mkdir -p "$phase_dir"

  bash loadtest/collect/snapshot_gateway_metrics.sh \
    "http://127.0.0.1:$GATEWAY_PORT" \
    "$phase_dir/gateway_metrics.txt" \
    || true

  "$PYTHON_BIN" loadtest/collect/snapshot_redis_breaker_state.py \
    --redis-url "redis://127.0.0.1:$REDIS_PORT/0" \
    --key-prefix "week4:resource-exhaustion" \
    --output "$phase_dir/redis_breaker_state.json" \
    || true

  bash loadtest/collect/snapshot_runtime.sh \
    "$phase_dir/runtime.txt" \
    || true
}

request_gateway() {
  local phase="$1"

  "$PYTHON_BIN" - "$phase" "$RUN_DIR" "$GATEWAY_PORT" <<'PY_REQUEST'
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

phase, run_dir, gateway_port = sys.argv[1:]

payload = {
    "prompt": "受控 CUDA OOM 故障注入验证。",
    "max_new_tokens": 8,
    "temperature": 0.0,
    "thinking_budget": 512,
}

request = urllib.request.Request(
    f"http://127.0.0.1:{gateway_port}/generate",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

record = {"phase": phase}

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        record["http_status"] = response.status
        record["payload"] = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    record["http_status"] = exc.code
    record["payload"] = json.loads(exc.read().decode("utf-8"))
except Exception as exc:
    record["http_status"] = None
    record["error"] = f"{type(exc).__name__}: {exc}"

path = Path(run_dir) / phase / "gateway_response.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(
    json.dumps(record, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(json.dumps(record, ensure_ascii=False))

raise SystemExit(0 if record.get("http_status") == 200 else 2)
PY_REQUEST
}

validate_results() {
  "$PYTHON_BIN" - "$RUN_DIR" <<'PY_VALIDATE'
import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])

expected = {
    "resource_exhausted_fallback": ("fallback", 1, 512),
    "breaker_open_fallback": ("fallback", 0, 512),
    "primary_recovered": ("primary", 1, None),
}

errors = []
phases = {}

for phase, expected_values in expected.items():
    payload = json.loads(
        (run_dir / phase / "gateway_response.json").read_text(encoding="utf-8")
    )
    body = payload["payload"]
    actual = (
        body.get("route"),
        body.get("primary_attempts"),
        body.get("fallback_thinking_budget"),
    )

    phases[phase] = {
        "expected": expected_values,
        "actual": actual,
    }

    if actual != expected_values:
        errors.append(
            f"{phase}: expected={expected_values}, actual={actual}"
        )

result = {
    "validation_passed": not errors,
    "errors": errors,
    "phases": phases,
    "boundary": (
        "确定性 HTTP 500 CUDA-OOM fault injection；验证错误分类、"
        "Redis breaker、fallback 与 recovery；不等同于真实 GPU OOM。"
    ),
}

(run_dir / "harness_validation.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if not errors else 2)
PY_VALIDATE
}

main() {
  if ! start_redis; then
    return $?
  fi

  if ! wait_redis; then
    return 22
  fi

  start_primary resource-exhausted
  start_fallback

  if ! wait_http "http://127.0.0.1:$PRIMARY_PORT/v1/models" "primary_fault"; then
    return 23
  fi

  if ! wait_http "http://127.0.0.1:$FALLBACK_PORT/v1/models" "fallback"; then
    return 24
  fi

  (
    INFERENCE_BACKEND=vllm \
    VLLM_BASE_URL="http://127.0.0.1:$PRIMARY_PORT/v1" \
    VLLM_MODEL_NAME="Seed-OSS-primary-controlled" \
    VLLM_TIMEOUT_SECONDS=10 \
    VLLM_FALLBACK_BASE_URL="http://127.0.0.1:$FALLBACK_PORT/v1" \
    VLLM_FALLBACK_MODEL_NAME="Seed-OSS-fallback-controlled" \
    VLLM_FALLBACK_TIMEOUT_SECONDS=10 \
    VLLM_ENABLE_SEED_THINKING_BUDGET=true \
    RESILIENCE_STATE_STORE=redis \
    RESILIENCE_REDIS_URL="redis://127.0.0.1:$REDIS_PORT/0" \
    RESILIENCE_REDIS_KEY_PREFIX="week4:resource-exhaustion" \
    RESILIENCE_FAILURE_THRESHOLD=1 \
    RESILIENCE_RETRY_ATTEMPTS=1 \
    RESILIENCE_RETRY_BACKOFF_SECONDS=0 \
    RESILIENCE_RECOVERY_TIMEOUT_SECONDS="$RECOVERY_TIMEOUT_SECONDS" \
    RESILIENCE_REDIS_PROBE_LEASE_MS=30000 \
    FASTAPI_PORT="$GATEWAY_PORT" \
    bash deployment/cloud/run_week4_gateway.sh
  ) > "$RUN_DIR/gateway.log" 2>&1 &

  GATEWAY_PID=$!

  if ! wait_http "http://127.0.0.1:$GATEWAY_PORT/health" "gateway"; then
    return 25
  fi

  for phase in resource_exhausted_fallback breaker_open_fallback; do
    mkdir -p "$RUN_DIR/$phase"
    if ! request_gateway "$phase"; then
      return 26
    fi
    snapshot_phase "$phase"
  done

  kill -TERM "$PRIMARY_PID" 2>/dev/null || true
  wait "$PRIMARY_PID" 2>/dev/null || true
  PRIMARY_PID=""

  start_primary success

  if ! wait_http "http://127.0.0.1:$PRIMARY_PORT/v1/models" "primary_recovered"; then
    return 27
  fi

  sleep "$((RECOVERY_TIMEOUT_SECONDS + 1))"

  mkdir -p "$RUN_DIR/primary_recovered"
  if ! request_gateway primary_recovered; then
    return 28
  fi
  snapshot_phase primary_recovered

  if ! validate_results; then
    return 29
  fi

  echo "RESOURCE_EXHAUSTION_HARNESS_PASSED run_dir=$RUN_DIR"
}

main
