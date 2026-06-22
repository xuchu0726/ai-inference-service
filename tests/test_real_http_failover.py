import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from fastapi.testclient import TestClient

import app.inference as inference_module
from app.backends.vllm_backend import VLLMBackend
from app.main import app
from app.resilience import CircuitBreaker, ResilienceController


def _start_server(handler_class):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop_server(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _json_response(handler, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def test_real_http_timeout_opens_breaker_and_routes_to_independent_fallback(
    monkeypatch,
):
    state = {
        "primary_requests": 0,
        "fallback_payloads": [],
    }

    class SlowPrimaryHandler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(content_length)

            state["primary_requests"] += 1
            time.sleep(0.15)

            try:
                _json_response(
                    self,
                    {
                        "choices": [{"message": {"content": "late primary"}}],
                        "usage": {},
                    },
                )
            except (BrokenPipeError, ConnectionResetError):
                pass

    class FallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_POST(self):
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(
                self.rfile.read(content_length).decode("utf-8")
            )
            state["fallback_payloads"].append(payload)

            _json_response(
                self,
                {
                    "choices": [{"message": {"content": "fallback answer"}}],
                    "usage": {
                        "prompt_tokens": 3,
                        "completion_tokens": 2,
                        "total_tokens": 5,
                    },
                },
            )

    primary_server, primary_thread = _start_server(SlowPrimaryHandler)
    fallback_server, fallback_thread = _start_server(FallbackHandler)

    try:
        primary_url = (
            f"http://127.0.0.1:{primary_server.server_port}/v1"
        )
        fallback_url = (
            f"http://127.0.0.1:{fallback_server.server_port}/v1"
        )

        monkeypatch.setattr(
            inference_module,
            "backend",
            VLLMBackend(
                base_url=primary_url,
                model_name="ByteDance-Seed/Seed-OSS-36B-Instruct",
                timeout_seconds=0.03,
                enable_seed_thinking_budget=True,
            ),
        )
        monkeypatch.setattr(
            inference_module,
            "fallback_backend",
            VLLMBackend(
                base_url=fallback_url,
                model_name="ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8",
                timeout_seconds=1,
                enable_seed_thinking_budget=True,
            ),
        )
        monkeypatch.setattr(
            inference_module,
            "resilience_controller",
            ResilienceController(
                breaker=CircuitBreaker(
                    failure_threshold=1,
                    recovery_timeout_seconds=60,
                ),
                retry_attempts=1,
                retry_backoff_seconds=0,
            ),
        )
        monkeypatch.setattr(
            inference_module,
            "RESILIENCE_FALLBACK_THINKING_BUDGET",
            512,
        )

        client = TestClient(app)

        first = client.post(
            "/generate",
            json={
                "prompt": "first request",
                "max_new_tokens": 8,
                "temperature": 0.0,
                "thinking_budget": 1024,
            },
        )
        second = client.post(
            "/generate",
            json={
                "prompt": "second request",
                "max_new_tokens": 8,
                "temperature": 0.0,
                "thinking_budget": 1024,
            },
        )

        assert first.status_code == 200
        assert first.json()["route"] == "fallback"
        assert first.json()["primary_attempts"] == 2
        assert first.json()["fallback_thinking_budget"] == 512

        assert second.status_code == 200
        assert second.json()["route"] == "fallback"
        assert second.json()["primary_attempts"] == 0

        assert state["primary_requests"] == 2
        assert len(state["fallback_payloads"]) == 2

        for payload in state["fallback_payloads"]:
            assert payload["model"] == (
                "ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8"
            )
            assert payload["chat_template_kwargs"] == {
                "thinking_budget": 512
            }

    finally:
        _stop_server(primary_server, primary_thread)
        _stop_server(fallback_server, fallback_thread)
