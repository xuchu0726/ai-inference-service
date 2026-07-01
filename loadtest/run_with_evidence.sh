#!/usr/bin/env bash
set -euo pipefail

# 用法：
# bash loadtest/run_with_evidence.sh \
#   jobs 100 60 200 http://127.0.0.1:8000 \
#   redis://127.0.0.1:6379/0 ai-inference:week4:jobs week4-workers \
#   evidence/week4_loadtest/jobs_qps100

MODE="${1:?mode is required}"
TARGET_QPS="${2:?target_qps is required}"
DURATION_SECONDS="${3:?duration_seconds is required}"
THREADS="${4:?threads is required}"
BASE_URL="${5:?base_url is required}"
REDIS_URL="${6:?redis_url is required}"
QUEUE_PREFIX="${7:?queue_prefix is required}"
CONSUMER_GROUP="${8:?consumer_group is required}"
OUTPUT_DIR="${9:?output_dir is required}"

RAMP_SECONDS="${RAMP_SECONDS:-10}"
WARMUP_SECONDS="${WARMUP_SECONDS:-$RAMP_SECONDS}"
MAX_RELATIVE_QPS_DEVIATION="${MAX_RELATIVE_QPS_DEVIATION:-0.10}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-0.01}"
MIN_STABLE_WINDOW_SAMPLES="${MIN_STABLE_WINDOW_SAMPLES:-1}"

read -r HOST PORT <<EOF
$(python - "$BASE_URL" <<'PY'
from urllib.parse import urlparse
import sys

parsed = urlparse(sys.argv[1])
if parsed.scheme not in {"http", "https"} or not parsed.hostname:
    raise SystemExit("base_url must include http:// or https:// and a host")

print(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
PY
)
EOF

mkdir -p "$OUTPUT_DIR"

{
  echo "mode=$MODE"
  echo "target_qps=$TARGET_QPS"
  echo "duration_seconds=$DURATION_SECONDS"
  echo "threads=$THREADS"
  echo "base_url=$BASE_URL"
  echo "redis_url=$REDIS_URL"
  echo "queue_prefix=$QUEUE_PREFIX"
  echo "consumer_group=$CONSUMER_GROUP"
  echo "git_commit=$(git rev-parse HEAD)"
  echo "ramp_seconds=$RAMP_SECONDS"
  echo "warmup_seconds=$WARMUP_SECONDS"
  echo "max_relative_qps_deviation=$MAX_RELATIVE_QPS_DEVIATION"
  echo "max_error_rate=$MAX_ERROR_RATE"
  echo "min_stable_window_samples=$MIN_STABLE_WINDOW_SAMPLES"
} > "$OUTPUT_DIR/run_config.txt"

bash loadtest/collect/snapshot_runtime.sh \
  "$OUTPUT_DIR/runtime_before.txt"

bash loadtest/collect/snapshot_gateway_metrics.sh \
  "$BASE_URL" \
  "$OUTPUT_DIR/gateway_metrics_before.txt"

python loadtest/collect/snapshot_redis_state.py \
  --redis-url "$REDIS_URL" \
  --queue-prefix "$QUEUE_PREFIX" \
  --consumer-group "$CONSUMER_GROUP" \
  --output "$OUTPUT_DIR/redis_before.json"

set +e
RAMP_SECONDS="$RAMP_SECONDS" \
bash loadtest/run_jmeter.sh \
  "$MODE" \
  "$TARGET_QPS" \
  "$DURATION_SECONDS" \
  "$THREADS" \
  "$HOST" \
  "$PORT" \
  "$OUTPUT_DIR/jmeter"
JMETER_RC=$?
set -e

bash loadtest/collect/snapshot_gateway_metrics.sh \
  "$BASE_URL" \
  "$OUTPUT_DIR/gateway_metrics_after.txt"

python loadtest/collect/snapshot_redis_state.py \
  --redis-url "$REDIS_URL" \
  --queue-prefix "$QUEUE_PREFIX" \
  --consumer-group "$CONSUMER_GROUP" \
  --output "$OUTPUT_DIR/redis_after.json"

bash loadtest/collect/snapshot_runtime.sh \
  "$OUTPUT_DIR/runtime_after.txt"

LOAD_PROFILE_RC=1

if [ -f "$OUTPUT_DIR/jmeter/results.jtl" ]; then
  python loadtest/collect/summarize_jtl.py \
    --jtl "$OUTPUT_DIR/jmeter/results.jtl" \
    --output "$OUTPUT_DIR/jmeter_summary.json" \
    --mode "$MODE" \
    --target-qps "$TARGET_QPS" \
    --configured-threads "$THREADS"

  set +e
  python loadtest/collect/validate_load_profile.py \
    --jtl "$OUTPUT_DIR/jmeter/results.jtl" \
    --output "$OUTPUT_DIR/load_profile_validation.json" \
    --target-qps "$TARGET_QPS" \
    --warmup-seconds "$WARMUP_SECONDS" \
    --max-relative-qps-deviation "$MAX_RELATIVE_QPS_DEVIATION" \
    --max-error-rate "$MAX_ERROR_RATE" \
    --min-samples "$MIN_STABLE_WINDOW_SAMPLES" \
    --fail-on-invalid
  LOAD_PROFILE_RC=$?
  set -e

  echo "load_profile_exit_code=$LOAD_PROFILE_RC" \
    | tee "$OUTPUT_DIR/load_profile_exit_code.txt"
else
  echo "results.jtl missing; JMeter exit code=$JMETER_RC" >&2
fi

echo "jmeter_exit_code=$JMETER_RC" \
  | tee "$OUTPUT_DIR/jmeter_exit_code.txt"

if [ "$JMETER_RC" -ne 0 ] || [ "$LOAD_PROFILE_RC" -ne 0 ]; then
  false
fi
