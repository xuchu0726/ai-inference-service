#!/usr/bin/env bash
set -euo pipefail

URL="${URL:-http://127.0.0.1:8000/generate}"
MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-128}"
THINKING_BUDGETS="${THINKING_BUDGETS:-512}"
REPEAT="${REPEAT:-2}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-900}"
CONCURRENCY_VALUES="${CONCURRENCY_VALUES:-1 2 4 8 16}"

mkdir -p results logs

echo "===== Week2 concurrency benchmark matrix ====="
echo "URL=${URL}"
echo "MAX_NEW_TOKENS=${MAX_NEW_TOKENS}"
echo "THINKING_BUDGETS=${THINKING_BUDGETS}"
echo "REPEAT=${REPEAT}"
echo "TIMEOUT_SECONDS=${TIMEOUT_SECONDS}"
echo "CONCURRENCY_VALUES=${CONCURRENCY_VALUES}"

for c in ${CONCURRENCY_VALUES}; do
  echo
  echo "===== Running concurrency=${c} ====="

  python scripts/benchmark_vllm_backend.py \
    --url "${URL}" \
    --output "results/week2_concurrency_c${c}.csv" \
    --concurrency "${c}" \
    --repeat "${REPEAT}" \
    --max-new-tokens "${MAX_NEW_TOKENS}" \
    --thinking-budgets "${THINKING_BUDGETS}" \
    --timeout-seconds "${TIMEOUT_SECONDS}" \
    2>&1 | tee "logs/week2_concurrency_c${c}.log"

  python scripts/analyze_vllm_benchmark.py \
    --input "results/week2_concurrency_c${c}.csv" \
    --output "results/week2_concurrency_c${c}_summary.csv"
done

echo
echo "===== Week2 concurrency matrix completed ====="
ls -lh results/week2_concurrency_c*.csv results/week2_concurrency_c*_summary.csv
