import time
import requests

URL = "http://127.0.0.1:8000/generate"

prompts = [
    "请用三句话解释什么是大模型推理。",
    "请总结下面这段法律文本的核心风险点。",
    "Explain KV Cache in LLM inference in simple terms.",
]

for i, prompt in enumerate(prompts, start=1):
    payload = {
        "prompt": prompt,
        "max_new_tokens": 128,
        "temperature": 0.7,
        "thinking_budget": 128,
    }

    start = time.time()
    response = requests.post(URL, json=payload, timeout=30)
    elapsed = time.time() - start

    print(f"\nCase {i}")
    print(f"Status: {response.status_code}")
    print(f"Client latency: {elapsed:.4f}s")
    print(response.json())
