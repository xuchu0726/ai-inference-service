#!/usr/bin/env python3
"""用于 Week4 容错验证的最小 OpenAI-compatible upstream fault server。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    mode = "success"
    model_name = "mock-model"

    def log_message(self, format: str, *args) -> None:
        return

    def _write_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/v1/models":
            self._write_json(
                200,
                {
                    "object": "list",
                    "data": [{"id": self.model_name, "object": "model"}],
                },
            )
            return
        self._write_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._write_json(404, {"error": {"message": "not found"}})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length:
            self.rfile.read(content_length)

        if self.mode == "resource-exhausted":
            self._write_json(
                500,
                {
                    "error": {
                        "message": (
                            "CUDA out of memory while allocating KV cache "
                            "for controlled Week4 fault injection"
                        ),
                        "type": "server_error",
                    }
                },
            )
            return

        self._write_json(
            200,
            {
                "id": "mock-success",
                "object": "chat.completion",
                "model": self.model_name,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"{self.mode} upstream response",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 4,
                    "total_tokens": 8,
                },
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument(
        "--mode",
        choices=("success", "resource-exhausted"),
        required=True,
    )
    parser.add_argument("--model-name", required=True)
    args = parser.parse_args()

    Handler.mode = args.mode
    Handler.model_name = args.model_name

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        json.dumps(
            {
                "host": args.host,
                "port": args.port,
                "mode": args.mode,
                "model_name": args.model_name,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
