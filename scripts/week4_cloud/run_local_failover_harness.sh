#!/usr/bin/env bash
# 本地 failover/recovery 集成验证。
# 该脚本仅使用两个 mock OpenAI upstream；不代表真实 GPU 性能。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${1:-tmp/week4_local_failover_harness_$STAMP}"

GATEWAY_PORT="${GATEWAY_PORT:-18000}"
PRIMARY_PORT="${PRIMARY_PORT:-18001}"
FALLBACK_PORT="${FALLBACK_PORT:-18002}"

REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
BREAKER_PREFIX="ai-inference:week4:local-failover:$STAMP"

PRIMARY_PID=""
FALLBACK_PID=""
GATEWAY_PID=""

cleanup() {
  for pid in "$GATEWAY_PID" "$PRIMARY_PID" "$FALLBACK_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup EXIT

mkdir -p "$RUN_DIR"

if ! python - "$REDIS_URL" <<'PY'
import sys
import redis

redis.Redis.from_url(sys.argv[1], socket_timeout=1).ping()
PY
then
  echo "redis_ready=no"
  exit 2
fi

echo "redis_ready=yes"
echo "run_dir=$RUN_DIR"
echo "breaker_prefix=$BREAKER_PREFIX"

start_primary() {
  python scripts/week4_cloud/mock_openai_upstream.py \
    --port "$PRIMARY_PORT" \
    --name primary \
    > "$RUN_DIR/primary.log" 2>&1 &
  PRIMARY_PID=$!
}

start_fallback() {
  python scripts/week4_cloud/mock_openai_upstream.py \
    --port "$FALLBACK_PORT" \
    --name fallback \
    > "$RUN_DIR/fallback.log" 2>&1 &
  FALLBACK_PID=$!
}

wait_http() {
  local url="$1"
  local label="$2"

  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "${label}_ready=yes"
      return 0
    fi
    sleep 0.1
  done

  echo "${label}_ready=no"
  return 1
}

snapshot_phase() {
  local phase="$1"
  local phase_dir="$RUN_DIR/$phase"

  mkdir -p "$phase_dir"

  bash loadtest/collect/snapshot_gateway_metrics.sh \
    "http://127.0.0.1:$GATEWAY_PORT" \
    "$phase_dir/gateway_metrics.txt" \
    || true

  python loadtest/collect/snapshot_redis_breaker_state.py \
    --redis-url "$REDIS_URL" \
    --key-prefix "$BREAKER_PREFIX" \
    --output "$phase_dir/redis_breaker_state.json" \
    || true

  bash loadtest/collect/snapshot_runtime.sh \
    "$phase_dir/runtime.txt" \
    || true
}

run_probe() {
  local phase="$1"
  local requests="$2"

  python scripts/week4_cloud/probe_gateway_failover.py \
    --base-url "http://127.0.0.1:$GATEWAY_PORT" \
    --requests "$requests" \
    --interval-seconds 0.1 \
    --max-new-tokens 8 \
    --output-dir "$RUN_DIR/$phase"
}

start_primary
start_fallback

wait_http "http://127.0.0.1:$PRIMARY_PORT/v1/models" "primary" || exit 3
wait_http "http://127.0.0.1:$FALLBACK_PORT/v1/models" "fallback" || exit 4

(
  INFERENCE_BACKEND=vllm \
  VLLM_BASE_URL="http://127.0.0.1:$PRIMARY_PORT/v1" \
  VLLM_MODEL_NAME="mock-primary" \
  VLLM_TIMEOUT_SECONDS=2 \
  VLLM_FALLBACK_BASE_URL="http://127.0.0.1:$FALLBACK_PORT/v1" \
  VLLM_FALLBACK_MODEL_NAME="mock-fallback" \
  VLLM_FALLBACK_TIMEOUT_SECONDS=5 \
  VLLM_ENABLE_SEED_THINKING_BUDGET=false \
  RESILIENCE_STATE_STORE=redis \
  RESILIENCE_REDIS_URL="$REDIS_URL" \
  RESILIENCE_REDIS_KEY_PREFIX="$BREAKER_PREFIX" \
  RESILIENCE_FAILURE_THRESHOLD=1 \
  RESILIENCE_RETRY_ATTEMPTS=1 \
  RESILIENCE_RETRY_BACKOFF_SECONDS=0.1 \
  RESILIENCE_RECOVERY_TIMEOUT_SECONDS=3 \
  RESILIENCE_REDIS_PROBE_LEASE_MS=5000 \
  exec python -m uvicorn app.main:app \
    --host 127.0.0.1 \
    --port "$GATEWAY_PORT"
) > "$RUN_DIR/gateway.log" 2>&1 &
GATEWAY_PID=$!

wait_http "http://127.0.0.1:$GATEWAY_PORT/health" "gateway" || exit 5

echo "===== phase baseline_primary ====="
run_probe "baseline_primary" 2
snapshot_phase "baseline_primary"

echo "===== phase primary_killed ====="
kill -TERM "$PRIMARY_PID" 2>/dev/null || true
wait "$PRIMARY_PID" 2>/dev/null || true
PRIMARY_PID=""
run_probe "primary_killed" 1
snapshot_phase "primary_killed"

echo "===== phase breaker_open_fallback ====="
run_probe "breaker_open_fallback" 1
snapshot_phase "breaker_open_fallback"

echo "===== phase primary_recovered ====="
start_primary
wait_http "http://127.0.0.1:$PRIMARY_PORT/v1/models" "primary_restarted" || exit 6
sleep 4
run_probe "primary_recovered" 1
snapshot_phase "primary_recovered"

python - "$RUN_DIR" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

run_dir = Path(sys.argv[1])

expectations = {
    "baseline_primary": [("primary", 1), ("primary", 1)],
    "primary_killed": [("fallback", 2)],
    "breaker_open_fallback": [("fallback", 0)],
    "primary_recovered": [("primary", 1)],
}

errors: list[str] = []
phase_summary: dict[str, object] = {}

for phase, expected in expectations.items():
    path = run_dir / phase / "probe_summary.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    actual = [
        (item["route"], item["primary_attempts"])
        for item in payload["results"]
    ]
    phase_summary[phase] = {
        "expected": expected,
        "actual": actual,
        "success_count": payload["success_count"],
        "failure_count": payload["failure_count"],
    }

    if actual != expected:
        errors.append(f"{phase}: expected={expected}, actual={actual}")

result = {
    "validation_passed": not errors,
    "errors": errors,
    "phases": phase_summary,
}

(run_dir / "harness_validation.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(json.dumps(result, ensure_ascii=False, indent=2))

if errors:
    raise SystemExit(2)
PY
