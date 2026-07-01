#!/usr/bin/env python3
"""用于本地 Week4 failover harness 的最小 OpenAI-compatible mock upstream。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def send_json(self, status: int, payload: dict[str, object]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/v1/models":
                self.send_json(
                    200,
                    {"data": [{"id": f"mock-{args.name}"}]},
                )
                return

            self.send_json(404, {"detail": "not found"})

        def do_POST(self) -> None:
            if self.path != "/v1/chat/completions":
                self.send_json(404, {"detail": "not found"})
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(content_length)

            self.send_json(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": f"mock response from {args.name}"
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 4,
                        "completion_tokens": 4,
                        "total_tokens": 8,
                    },
                },
            )

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"mock_upstream_ready=name={args.name} "
        f"host={args.host} port={args.port}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
