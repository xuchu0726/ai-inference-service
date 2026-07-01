#!/usr/bin/env bash
set -euo pipefail

# 用法：
# bash loadtest/collect/snapshot_runtime.sh evidence/week4_loadtest/example/runtime.txt

OUTPUT_FILE="${1:?usage: snapshot_runtime.sh <output_file>}"

mkdir -p "$(dirname "$OUTPUT_FILE")"

{
  echo "===== collected_at_utc ====="
  date -u +"%Y-%m-%dT%H:%M:%SZ"

  echo
  echo "===== uname ====="
  uname -a

  echo
  echo "===== process ====="
  ps -ax -o pid=,ppid=,command= \
    | grep -E '[u]vicorn|[a]pp\.job_worker|[v]llm|[r]edis-server' \
    || true

  echo
  echo "===== nvidia_smi ====="
  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi
  else
    echo "nvidia_smi=unavailable"
  fi

  echo
  echo "===== git_commit ====="
  git rev-parse HEAD

  echo
  echo "===== git_status ====="
  git status --short
} > "$OUTPUT_FILE"

echo "runtime_snapshot=$OUTPUT_FILE"
