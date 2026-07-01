#!/usr/bin/env bash
set -euo pipefail

# 用法：
# bash loadtest/run_jmeter.sh jobs 100 60 200 127.0.0.1 8000 results/week4/jobs_qps100
#
# 参数：
# 1. mode: jobs 或 generate
# 2. target_qps: jobs 模式目标 QPS；generate 模式填 0
# 3. duration_seconds
# 4. threads
# 5. host
# 6. port
# 7. output_dir

MODE="${1:?mode is required}"
TARGET_QPS="${2:?target_qps is required}"
DURATION_SECONDS="${3:?duration_seconds is required}"
THREADS="${4:?threads is required}"
HOST="${5:?host is required}"
PORT="${6:?port is required}"
OUTPUT_DIR="${7:?output_dir is required}"
RAMP_SECONDS="${RAMP_SECONDS:-1}"

case "$MODE" in
  jobs)
    SOURCE_PLAN="loadtest/jmeter/jobs_admission.jmx"
    ;;
  generate)
    SOURCE_PLAN="loadtest/jmeter/generate_short.jmx"
    ;;
  *)
    echo "unsupported mode: $MODE" >&2
    false
    ;;
esac

mkdir -p "$OUTPUT_DIR"
rm -rf "$OUTPUT_DIR/html-report"

if [ "$MODE" = "jobs" ]; then
  TARGET_RPM=$((TARGET_QPS * 60))

  python - "$SOURCE_PLAN" "$OUTPUT_DIR/test_plan.jmx" "$TARGET_RPM" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1])
target = Path(sys.argv[2])
target_rpm = float(sys.argv[3])

text = source.read_text(encoding="utf-8")
old = "<value>6000.0</value>"
new = f"<value>{target_rpm:.1f}</value>"

if old not in text:
    raise SystemExit("jobs throughput placeholder 6000.0 not found")

target.write_text(text.replace(old, new, 1), encoding="utf-8")
PY
else
  cp "$SOURCE_PLAN" "$OUTPUT_DIR/test_plan.jmx"
fi

jmeter -n \
  -j "$OUTPUT_DIR/jmeter.log" \
  -t "$OUTPUT_DIR/test_plan.jmx" \
  -Jhost="$HOST" \
  -Jport="$PORT" \
  -Jthreads="$THREADS" \
  -Jramp_seconds="$RAMP_SECONDS" \
  -Jduration_seconds="$DURATION_SECONDS" \
  -Jmax_new_tokens=8 \
  -l "$OUTPUT_DIR/results.jtl" \
  -e -o "$OUTPUT_DIR/html-report" \
  > "$OUTPUT_DIR/jmeter_stdout.log" 2>&1

echo "mode=$MODE"
echo "target_qps=$TARGET_QPS"
echo "duration_seconds=$DURATION_SECONDS"
echo "threads=$THREADS"
echo "ramp_seconds=$RAMP_SECONDS"
echo "output_dir=$OUTPUT_DIR"
