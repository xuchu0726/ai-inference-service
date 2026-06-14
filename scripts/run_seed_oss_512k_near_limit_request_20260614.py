import json
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

from transformers import AutoTokenizer

MODEL_NAME = "ByteDance-Seed/Seed-OSS-36B-Instruct"
MODEL_SNAPSHOT = "/workspace/hf_cache/models--ByteDance-Seed--Seed-OSS-36B-Instruct/snapshots/497f1dca95ebdec98e41d517b9f060ee753c902f"
URL = "http://127.0.0.1:8002/v1/chat/completions"

TARGET_INPUT_TOKENS = 500_000
MAX_MODEL_LEN = 524_288
MAX_OUTPUT_TOKENS = 32

OUT_DIR = Path("results/week2_hardening")
EVID_DIR = Path("evidence/week2_hardening")
OUT_DIR.mkdir(parents=True, exist_ok=True)
EVID_DIR.mkdir(parents=True, exist_ok=True)

request_path = OUT_DIR / "seed_oss_4xa100_512k_near_limit_request_20260614.json"
response_path = OUT_DIR / "seed_oss_4xa100_512k_near_limit_response_20260614.json"
summary_path = OUT_DIR / "seed_oss_4xa100_512k_near_limit_summary_20260614.json"

print("===== Seed-OSS 512K near-limit request generation =====", flush=True)
print("time:", datetime.utcnow().isoformat() + "Z", flush=True)
print("model:", MODEL_NAME, flush=True)
print("target_input_tokens:", TARGET_INPUT_TOKENS, flush=True)

tokenizer = AutoTokenizer.from_pretrained(MODEL_SNAPSHOT, trust_remote_code=True)

block = (
    "This is a deterministic long-context validation block for Seed-OSS 512K serving. "
    "The purpose is to stress prefill, KV cache allocation, and OpenAI-compatible API stability. "
    "Remember the final answer must be exactly: 512K near-limit context test passed. "
)

# Build by token budget, then trim by binary search.
text = block
while len(tokenizer.encode(text, add_special_tokens=False)) < TARGET_INPUT_TOKENS:
    text += block * 256

lo, hi = 0, len(text)
best = text
best_tokens = len(tokenizer.encode(best, add_special_tokens=False))

while lo <= hi:
    mid = (lo + hi) // 2
    candidate = text[:mid]
    n = len(tokenizer.encode(candidate, add_special_tokens=False))
    if n <= TARGET_INPUT_TOKENS:
        best = candidate
        best_tokens = n
        lo = mid + 1
    else:
        hi = mid - 1

prompt = (
    best
    + "\n\nFinal instruction: Reply with exactly this sentence and nothing else: "
      "512K near-limit context test passed."
)

prompt_tokens_est = len(tokenizer.encode(prompt, add_special_tokens=False))
print("constructed_prompt_tokens_est:", prompt_tokens_est, flush=True)

payload = {
    "model": MODEL_NAME,
    "messages": [
        {
            "role": "user",
            "content": prompt,
        }
    ],
    "max_tokens": MAX_OUTPUT_TOKENS,
    "temperature": 0,
}

with request_path.open("w", encoding="utf-8") as f:
    json.dump(
        {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "model": MODEL_NAME,
            "model_snapshot": MODEL_SNAPSHOT,
            "target_input_tokens": TARGET_INPUT_TOKENS,
            "constructed_prompt_tokens_est": prompt_tokens_est,
            "max_model_len": MAX_MODEL_LEN,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "request_note": "Full prompt omitted from summary; full request payload stored in this file.",
            "payload": payload,
        },
        f,
        ensure_ascii=False,
    )

print("request_payload_saved:", request_path, flush=True)
print("===== Sending request =====", flush=True)

body = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    URL,
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

start = time.time()
ok = False
status = None
response_text = ""

try:
    with urllib.request.urlopen(req, timeout=1800) as resp:
        status = resp.status
        response_text = resp.read().decode("utf-8", errors="replace")
        ok = 200 <= status < 300
except urllib.error.HTTPError as e:
    status = e.code
    response_text = e.read().decode("utf-8", errors="replace")
except Exception as e:
    status = "exception"
    response_text = repr(e)

latency_s = time.time() - start

try:
    response_json = json.loads(response_text)
except Exception:
    response_json = {"raw_response": response_text}

with response_path.open("w", encoding="utf-8") as f:
    json.dump(
        {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "ok": ok,
            "status": status,
            "latency_s": latency_s,
            "response": response_json,
        },
        f,
        ensure_ascii=False,
        indent=2,
    )

usage = response_json.get("usage", {}) if isinstance(response_json, dict) else {}
choices = response_json.get("choices", []) if isinstance(response_json, dict) else []
finish_reason = choices[0].get("finish_reason") if choices else None
content_preview = ""
if choices:
    content_preview = choices[0].get("message", {}).get("content", "")[:500]

summary = {
    "created_at": datetime.utcnow().isoformat() + "Z",
    "model": MODEL_NAME,
    "model_snapshot": MODEL_SNAPSHOT,
    "target_input_tokens": TARGET_INPUT_TOKENS,
    "constructed_prompt_tokens_est": prompt_tokens_est,
    "max_model_len": MAX_MODEL_LEN,
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "ok": ok,
    "status": status,
    "latency_s": latency_s,
    "usage": usage,
    "finish_reason": finish_reason,
    "content_preview": content_preview,
    "request_path": str(request_path),
    "response_path": str(response_path),
}

with summary_path.open("w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

print("===== Summary =====", flush=True)
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
