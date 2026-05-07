import json
import time
import urllib.request
import urllib.error
from pathlib import Path


FASTAPI_URL = "http://127.0.0.1:8000/generate"

payload = {
    "prompt": "请用三句话解释什么是大模型推理，并说明为什么 vLLM 适合做推理服务。",
    "max_new_tokens": 128,
    "temperature": 0.7,
    "thinking_budget": 512,
}

request = urllib.request.Request(
    FASTAPI_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

start = time.time()

try:
    with urllib.request.urlopen(request, timeout=300) as response:
        body = response.read().decode("utf-8")
        status = response.status
except urllib.error.HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    raise RuntimeError(f"HTTP {exc.code}: {body}") from exc

latency = time.time() - start
data = json.loads(body)

Path("results").mkdir(exist_ok=True)
Path("results/cloud_smoke_test_response.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print("status:", status)
print("client_latency_seconds:", round(latency, 6))
print(json.dumps(data, ensure_ascii=False, indent=2))
