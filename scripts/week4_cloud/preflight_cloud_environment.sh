#!/usr/bin/env bash
# Week4 云端 GPU 环境预检。
# 只检查环境，不启动 vLLM、Gateway、BAGEL 或压测。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT" || exit 1

EXPECTED_GPU_COUNT="${EXPECTED_GPU_COUNT:-4}"
MODEL_PATH="${MODEL_PATH:-}"
CHECK_BAGEL="${CHECK_BAGEL:-0}"

FAILURES=0

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    echo "CHECK_OK command=$name path=$(command -v "$name")"
  else
    echo "CHECK_FAIL command=$name reason=not_found"
    FAILURES=$((FAILURES + 1))
  fi
}

check_path() {
  local label="$1"
  local path="$2"

  if [ -e "$path" ]; then
    echo "CHECK_OK path=$label value=$path"
  else
    echo "CHECK_FAIL path=$label value=$path reason=missing"
    FAILURES=$((FAILURES + 1))
  fi
}

echo "===== timestamp ====="
date -Iseconds

echo
echo "===== repository ====="
echo "repo_root=$REPO_ROOT"
git rev-parse --short HEAD || true
git status --short || true

echo
echo "===== commands ====="
for command_name in nvidia-smi python redis-server redis-cli jmeter wrk docker; do
  check_command "$command_name"
done

echo
echo "===== GPU ====="
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.total,driver_version \
    --format=csv,noheader || {
      echo "CHECK_FAIL nvidia_smi=query_failed"
      FAILURES=$((FAILURES + 1))
    }

  GPU_COUNT="$(nvidia-smi --query-gpu=index --format=csv,noheader | wc -l | tr -d ' ')"
  echo "gpu_count=$GPU_COUNT expected_gpu_count=$EXPECTED_GPU_COUNT"

  if [ "$GPU_COUNT" -lt "$EXPECTED_GPU_COUNT" ]; then
    echo "CHECK_FAIL gpu_count=insufficient"
    FAILURES=$((FAILURES + 1))
  fi
fi

echo
echo "===== Python packages ====="
python - <<'PY'
import importlib
import sys

required = ["torch", "vllm", "triton", "redis", "fastapi"]
failed = 0

print("python_executable:", sys.executable)
print("python_version:", sys.version.replace("\n", " "))

for name in required:
    try:
        module = importlib.import_module(name)
        print(f"CHECK_OK package={name} version={getattr(module, '__version__', 'unknown')}")
    except Exception as exc:
        failed += 1
        print(f"CHECK_FAIL package={name} error={type(exc).__name__}: {exc}")

try:
    import torch
    print("torch_cuda_available:", torch.cuda.is_available())
    print("torch_cuda_version:", torch.version.cuda)
    print("torch_device_count:", torch.cuda.device_count())
except Exception as exc:
    failed += 1
    print(f"CHECK_FAIL torch_cuda error={type(exc).__name__}: {exc}")

raise SystemExit(failed)
PY

PYTHON_STATUS=$?
if [ "$PYTHON_STATUS" -ne 0 ]; then
  FAILURES=$((FAILURES + 1))
fi

echo
echo "===== model ====="
if [ -z "$MODEL_PATH" ]; then
  echo "CHECK_FAIL model_path=unset"
  FAILURES=$((FAILURES + 1))
else
  check_path "MODEL_PATH" "$MODEL_PATH"
  check_path "MODEL_CONFIG" "$MODEL_PATH/config.json"
fi

if [ "$CHECK_BAGEL" = "1" ]; then
  echo
  echo "===== BAGEL assets ====="
  BAGEL_ROOT="${BAGEL_ROOT:-/workspace/bagel_week3}"
  check_path "BAGEL_ROOT" "$BAGEL_ROOT"
  check_path "BAGEL_PYTHON" "${BAGEL_PYTHON:-$BAGEL_ROOT/venv/bin/python}"
  check_path "BAGEL_APP" "${BAGEL_APP:-$BAGEL_ROOT/vendor/BAGEL/app.py}"
  check_path "BAGEL_MODEL_PATH" "${BAGEL_MODEL_PATH:-$BAGEL_ROOT/models/BAGEL-7B-MoT}"
fi

echo
echo "===== result ====="
echo "failure_count=$FAILURES"

if [ "$FAILURES" -ne 0 ]; then
  exit 1
fi

echo "PREFLIGHT_PASSED"
