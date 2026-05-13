#!/usr/bin/env bash
set -euo pipefail

OUTPUT="${1:-logs/week2_nvidia_smi_sampling.csv}"
INTERVAL_SECONDS="${2:-5}"

mkdir -p "$(dirname "$OUTPUT")"

echo "timestamp,index,name,memory.used [MiB],memory.total [MiB],utilization.gpu [%],utilization.memory [%]" > "$OUTPUT"

echo "Sampling GPU metrics every ${INTERVAL_SECONDS}s"
echo "Output: ${OUTPUT}"
echo "Press Ctrl+C to stop."

nvidia-smi \
  --query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu,utilization.memory \
  --format=csv,noheader,nounits \
  -l "$INTERVAL_SECONDS" >> "$OUTPUT"
