#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

./scripts/week3_bagel/start_bagel_runtime.sh

for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:7860/ >/dev/null; then
    break
  fi
  sleep 2
done

curl -fsS http://127.0.0.1:7860/ >/dev/null
./scripts/week3_bagel/start_multimodal_api.sh

for _ in $(seq 1 15); do
  if curl -fsS http://127.0.0.1:8000/multimodal/health >/dev/null; then
    break
  fi
  sleep 2
done

curl -sS http://127.0.0.1:8000/multimodal/health
