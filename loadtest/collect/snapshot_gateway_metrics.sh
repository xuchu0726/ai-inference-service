#!/usr/bin/env bash
set -euo pipefail

# 用法：
# bash loadtest/collect/snapshot_gateway_metrics.sh \
#   http://127.0.0.1:8000 \
#   evidence/week4_loadtest/example/gateway_metrics.txt

BASE_URL="${1:?usage: snapshot_gateway_metrics.sh <base_url> <output_file>}"
OUTPUT_FILE="${2:?usage: snapshot_gateway_metrics.sh <base_url> <output_file>}"

mkdir -p "$(dirname "$OUTPUT_FILE")"

{
  echo "===== collected_at_utc ====="
  date -u +"%Y-%m-%dT%H:%M:%SZ"

  echo
  echo "===== source ====="
  echo "${BASE_URL%/}/metrics"

  echo
  echo "===== metrics ====="
  curl --fail --silent --show-error "${BASE_URL%/}/metrics"
} > "$OUTPUT_FILE"

echo "gateway_metrics_snapshot=$OUTPUT_FILE"
