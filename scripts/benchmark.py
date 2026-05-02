import csv
import time
from pathlib import Path

import requests

URL = "http://127.0.0.1:8000/generate"
OUTPUT_PATH = Path("results/mock_benchmark.csv")

prompts = [
    "请用三句话解释什么是大模型推理。",
    "请总结下面这段法律文本的核心风险点。",
    "Explain KV Cache in LLM inference in simple terms.",
]

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "case_id",
            "status_code",
            "client_latency_seconds",
            "server_latency_seconds",
            "input_chars",
            "max_new_tokens",
            "thinking_budget",
            "response",
        ],
    )
    writer.writeheader()

    for case_id, prompt in enumerate(prompts, start=1):
        payload = {
            "prompt": prompt,
            "max_new_tokens": 128,
            "temperature": 0.7,
            "thinking_budget": 128,
        }

        start = time.time()
        response = requests.post(URL, json=payload, timeout=30)
        client_latency = time.time() - start

        data = response.json()

        row = {
            "case_id": case_id,
            "status_code": response.status_code,
            "client_latency_seconds": round(client_latency, 6),
            "server_latency_seconds": data.get("latency_seconds"),
            "input_chars": data.get("input_chars"),
            "max_new_tokens": data.get("max_new_tokens"),
            "thinking_budget": data.get("thinking_budget"),
            "response": data.get("response"),
        }

        writer.writerow(row)

        print(f"\nCase {case_id}")
        print(f"Status: {response.status_code}")
        print(f"Client latency: {client_latency:.4f}s")
        print(data)

print(f"\nBenchmark results saved to: {OUTPUT_PATH}")