#!/usr/bin/env python3
"""
Local /generate adapter for Week2 W8A8 GSM8K evaluation.

It preserves the existing GSM8K benchmark script interface:
POST /generate
{
  "prompt": "...",
  "max_new_tokens": 256,
  "temperature": 0,
  "thinking_budget": 0
}

and forwards each request to the W8A8 vLLM OpenAI-compatible
/v1/chat/completions endpoint.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

MODEL_NAME = os.environ.get("W8A8_MODEL_NAME", "Seed-OSS-36B-Instruct-W8A8")
VLLM_URL = os.environ.get("W8A8_VLLM_URL", "http://127.0.0.1:8002/v1/chat/completions")
API_KEY = os.environ.get("VLLM_API_KEY", "")


class GenerateHandler(BaseHTTPRequestHandler):
    server_version = "W8A8GenerateAdapter/0.1"

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "model_name": MODEL_NAME, "upstream": VLLM_URL})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/generate":
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(length).decode("utf-8")
            req = json.loads(request_body) if request_body else {}

            prompt = str(req.get("prompt", ""))
            max_tokens = int(req.get("max_new_tokens", 256))
            temperature = float(req.get("temperature", 0.0))
            thinking_budget = int(req.get("thinking_budget", 0))

            eval_prompt = (
                "You are being evaluated on GSM8K exact-answer accuracy. "
                "Do not output <seed:think> tags. "
                "Use concise reasoning only. "
                "End the response exactly with: Final answer: <number>.\n\n"
                + prompt
            )

            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a concise math problem solver. "
                            "Do not output hidden thinking tags or verbose internal reasoning. "
                            "Always end with exactly: Final answer: <number>."
                        ),
                    },
                    {"role": "user", "content": eval_prompt},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "chat_template_kwargs": {"thinking_budget": thinking_budget},
            }

            headers = {"Content-Type": "application/json"}
            if API_KEY:
                headers["Authorization"] = f"Bearer {API_KEY}"

            upstream_request = urllib.request.Request(
                url=VLLM_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )

            start = time.perf_counter()
            with urllib.request.urlopen(upstream_request, timeout=1800) as response:
                latency = time.perf_counter() - start
                data = json.loads(response.read().decode("utf-8"))

            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {}) or {}
            text = message.get("content", "") or ""
            usage = data.get("usage", {}) or {}

            output_tokens = usage.get("completion_tokens")
            tokens_per_second = None
            if isinstance(output_tokens, (int, float)) and latency > 0:
                tokens_per_second = round(float(output_tokens) / latency, 6)

            result = {
                "response": text,
                "text": text,
                "generated_text": text,
                "backend": "vllm_w8a8",
                "model_name": MODEL_NAME,
                "device": "vllm_server",
                "input_tokens": usage.get("prompt_tokens"),
                "output_tokens": output_tokens,
                "tokens_per_second": tokens_per_second,
                "latency_seconds": latency,
                "server_latency_seconds": latency,
                "finish_reason": choice.get("finish_reason"),
                "upstream_id": data.get("id"),
                "system_fingerprint": data.get("system_fingerprint"),
            }
            self._send_json(200, result)

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            self._send_json(exc.code, {"error": error_body})
        except Exception as exc:
            self._send_json(500, {"error": repr(exc)})


def main() -> None:
    host = os.environ.get("W8A8_ADAPTER_HOST", "127.0.0.1")
    port = int(os.environ.get("W8A8_ADAPTER_PORT", "8010"))
    print(f"Starting adapter on http://{host}:{port}/generate")
    print(f"Forwarding to {VLLM_URL}")
    print(f"Model: {MODEL_NAME}")
    ThreadingHTTPServer((host, port), GenerateHandler).serve_forever()


if __name__ == "__main__":
    main()
