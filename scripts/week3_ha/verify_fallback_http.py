import json
import os
import sys
import urllib.error
import urllib.request

base_url = os.environ["FALLBACK_BASE_URL"].rstrip("/")
api_key = os.environ["FALLBACK_KEY"]
model_name = "Seed-OSS-36B-Instruct-W8A8-Fallback"

headers = {
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "ai-inference-gateway/1.0",
}

def request(url, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            **headers,
            **({"Content-Type": "application/json"} if body else {}),
        },
        method="POST" if body else "GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.status, json.loads(response.read())

try:
    status, models = request(f"{base_url}/models")
    print(f"models_http={status}")
    print("model_present=" + str(
        any(item.get("id") == model_name for item in models.get("data", []))
    ))

    status, completion = request(
        f"{base_url}/chat/completions",
        {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly: fallback-direct-ok",
                }
            ],
            "temperature": 0,
            "max_tokens": 8,
        },
    )
    print(f"chat_http={status}")
    print(
        "response="
        + completion["choices"][0]["message"]["content"].strip()
    )
except urllib.error.HTTPError as exc:
    print(f"http_error={exc.code}")
    print(exc.read().decode(errors="replace")[:500])
    sys.exit(1)
except Exception as exc:
    print(f"error={type(exc).__name__}: {exc}")
    sys.exit(1)
