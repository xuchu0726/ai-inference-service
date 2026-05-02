import csv
import time
from pathlib import Path

import requests

URL = "http://127.0.0.1:8000/generate"
OUTPUT_PATH = Path("results/thinking_budget_benchmark.csv")

prompts = [
    "请用三句话解释什么是大模型推理。",
    "请总结下面这段法律文本的核心风险点。",
    "Explain KV Cache in LLM inference in simple terms.",
]

thinking_budgets = [0, 128, 512, 1024]

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=[
            "case_id",
            "prompt_id",
            "thinking_budget",
            "status_code",
            "client_latency_seconds",
            "server_latency_seconds",
            "input_chars",
            "max_new_tokens",
            "response",
        ],
    )
    writer.writeheader()

    case_id = 1

    for prompt_id, prompt in enumerate(prompts, start=1):
        for budget in thinking_budgets:
            payload = {
                "prompt": prompt,
                "max_new_tokens": 128,
                "temperature": 0.7,
                "thinking_budget": budget,
            }

            start = time.time()
            response = requests.post(URL, json=payload, timeout=30)
            client_latency = time.time() - start

            data = response.json()

            row = {
                "case_id": case_id,
                "prompt_id": prompt_id,
                "thinking_budget": budget,
                "status_code": response.status_code,
                "client_latency_seconds": round(client_latency, 6),
                "server_latency_seconds": data.get("latency_seconds"),
                "input_chars": data.get("input_chars"),
                "max_new_tokens": data.get("max_new_tokens"),
                "response": data.get("response"),
            }

            writer.writerow(row)

            print(f"\nCase {case_id}")
            print(f"Prompt ID: {prompt_id}")
            print(f"Thinking budget: {budget}")
            print(f"Status: {response.status_code}")
            print(f"Client latency: {client_latency:.4f}s")
            print(data)

            case_id += 1

print(f"\nBenchmark results saved to: {OUTPUT_PATH}")