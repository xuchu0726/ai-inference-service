#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT="$ROOT/scripts/week3_bagel/run_understanding_benchmark.py"

for manifest in \
  data/week3_bagel/cases/official_meme.json \
  data/week3_bagel/cases/official_octupusy.json \
  data/week3_bagel/cases/official_women.json
do
  echo "===== AUDIT: $manifest ====="
  "$PYTHON_BIN" "$SCRIPT" \
    --runs 3 \
    --sample-interval 0.5 \
    --manifest "$manifest" \
    || exit 1
done
