#!/usr/bin/env bash
set -euo pipefail

REPO="/workspace/ai-inference-service"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE="$REPO/evidence/week4_cloud/${STAMP}_bootstrap_local_serving"
RUNTIME="/opt/venvs/vllm-0112-runtime"
SRC="/workspace/models/Seed-OSS-36B-Instruct-W8A8"
DST="/opt/models/Seed-OSS-36B-Instruct-W8A8-local"

mkdir -p "$EVIDENCE" /opt/venvs /opt/models

log() {
  printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$EVIDENCE/bootstrap.log"
}

fail() {
  rc="$?"
  log "BOOTSTRAP_FAILED rc=$rc"
  exit "$rc"
}
trap fail ERR

log "===== bootstrap start ====="
log "repo=$REPO"
log "source_model=$SRC"
log "local_model=$DST"
log "runtime=$RUNTIME"

{
  echo "===== disk ====="
  df -hT / /opt /workspace
  echo
  echo "===== gpu ====="
  nvidia-smi
  echo
  echo "===== source config null dtype fields ====="
  grep -nE '"(scale_dtype|zp_dtype)"[[:space:]]*:[[:space:]]*null' \
    "$SRC/config.json" || true
} > "$EVIDENCE/preflight.txt"

if ! command -v rsync >/dev/null 2>&1; then
  log "installing rsync"
  apt-get update >>"$EVIDENCE/bootstrap.log" 2>&1
  DEBIAN_FRONTEND=noninteractive apt-get install -y rsync \
    >>"$EVIDENCE/bootstrap.log" 2>&1
fi

log "===== stage model to local disk ====="
mkdir -p "$DST"
rsync -a --partial --append-verify --info=stats2 \
  "$SRC/" "$DST/" >>"$EVIDENCE/rsync.log" 2>&1

log "===== patch copied quantization config only ====="
TARGET_CONFIG="$DST/config.json" python3 - <<'PY' \
  >>"$EVIDENCE/bootstrap.log" 2>&1
import json
import os
from pathlib import Path

path = Path(os.environ["TARGET_CONFIG"])
config = json.loads(path.read_text(encoding="utf-8"))
groups = config["quantization_config"]["config_groups"]

removed = []
for group_name, group in groups.items():
    for section_name in ("weights", "input_activations"):
        section = group.get(section_name)
        if not isinstance(section, dict):
            continue
        for field in ("scale_dtype", "zp_dtype"):
            if section.get(field) is None and field in section:
                del section[field]
                removed.append(f"{group_name}.{section_name}.{field}")

path.write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print("removed_fields=" + ",".join(removed))
if len(removed) != 4:
    raise SystemExit(
        f"expected exactly 4 removed null dtype fields, got {len(removed)}"
    )
PY

log "===== rebuild pinned vLLM runtime ====="
rm -rf "$RUNTIME"
python3 -m venv "$RUNTIME"
source "$RUNTIME/bin/activate"

python -m pip install --upgrade pip setuptools wheel \
  >>"$EVIDENCE/pip_install.log" 2>&1

python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
  "torch==2.9.0+cu128" \
  "torchvision==0.24.0+cu128" \
  "torchaudio==2.9.0+cu128" \
  >>"$EVIDENCE/pip_install.log" 2>&1

python -m pip install \
  "vllm==0.11.2" \
  "pydantic==2.12.5" \
  "compressed-tensors==0.12.2" \
  "transformers==4.57.6" \
  >>"$EVIDENCE/pip_install.log" 2>&1

log "===== runtime self-check ====="
python - <<'PY' >"$EVIDENCE/runtime_versions.txt"
import torch
import vllm
import pydantic
import compressed_tensors
import transformers

print(f"torch={torch.__version__}")
print(f"vllm={vllm.__version__}")
print(f"pydantic={pydantic.__version__}")
print(f"compressed_tensors={compressed_tensors.__version__}")
print(f"transformers={transformers.__version__}")
print(f"cuda_available={torch.cuda.is_available()}")
print(f"gpu_count={torch.cuda.device_count()}")
PY

python -m pip check >"$EVIDENCE/pip_check.txt" 2>&1

{
  echo "===== target model ====="
  du -sh "$DST"
  echo
  echo "===== target config remaining null dtype fields ====="
  grep -nE '"(scale_dtype|zp_dtype)"[[:space:]]*:[[:space:]]*null' \
    "$DST/config.json" || true
  echo
  echo "===== runtime ====="
  cat "$EVIDENCE/runtime_versions.txt"
  echo
  echo "===== pip check ====="
  cat "$EVIDENCE/pip_check.txt"
} >"$EVIDENCE/final_verification.txt"

log "BOOTSTRAP_READY=1"
log "EVIDENCE_DIR=$EVIDENCE"
log "LOCAL_MODEL=$DST"
log "RUNTIME=$RUNTIME"
