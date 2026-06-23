import json

import app.backends.vllm_backend as vllm_module
from app.backends.vllm_backend import VLLMBackend


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_seed_oss_request_sends_budget_in_chat_template_kwargs(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        )

    monkeypatch.setattr(vllm_module.urllib.request, "urlopen", fake_urlopen)

    backend = VLLMBackend(
        base_url="http://fallback-vllm:8000/v1",
        model_name="ByteDance-Seed/Seed-OSS-36B-Instruct",
        timeout_seconds=12,
    )

    result = backend.generate(
        prompt="fallback validation",
        max_new_tokens=8,
        temperature=0.0,
        thinking_budget=512,
    )

    assert captured["url"] == "http://fallback-vllm:8000/v1/chat/completions"
    assert captured["timeout"] == 12
    assert captured["payload"]["model"] == "ByteDance-Seed/Seed-OSS-36B-Instruct"
    assert captured["payload"]["chat_template_kwargs"] == {
        "thinking_budget": 512
    }
    assert result["thinking_budget"] == 512


def test_seed_oss_low_nonzero_budget_is_normalized_to_zero(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }
        )

    monkeypatch.setattr(vllm_module.urllib.request, "urlopen", fake_urlopen)

    backend = VLLMBackend(
        base_url="http://fallback-vllm:8000/v1",
        model_name="ByteDance-Seed/Seed-OSS-36B-Instruct",
    )

    backend.generate(
        prompt="normalization validation",
        thinking_budget=256,
    )

    assert captured["payload"]["chat_template_kwargs"] == {
        "thinking_budget": 0
    }


def test_vllm_backend_sends_bearer_token_to_generate_and_readiness(
    monkeypatch,
):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(
            {
                "url": request.full_url,
                "authorization": request.headers.get("Authorization"),
                "content_type": request.headers.get("Content-type"),
                "user_agent": request.headers.get("User-agent"),
                "timeout": timeout,
            }
        )

        if request.full_url.endswith("/models"):
            return FakeResponse(
                {
                    "data": [
                        {
                            "id": "ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8"
                        }
                    ]
                }
            )

        return FakeResponse(
            {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {},
            }
        )

    monkeypatch.setattr(vllm_module.urllib.request, "urlopen", fake_urlopen)

    backend = VLLMBackend(
        base_url="https://primary.example/v1",
        model_name="ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8",
        timeout_seconds=12,
        api_key="test-primary-token",
    )

    backend.generate(prompt="auth validation")
    readiness = backend.check_ready()

    assert captured[0]["url"] == "https://primary.example/v1/chat/completions"
    assert captured[0]["authorization"] == "Bearer test-primary-token"
    assert captured[0]["content_type"] == "application/json"
    assert captured[0]["user_agent"] == "ai-inference-gateway/1.0"

    assert captured[1]["url"] == "https://primary.example/v1/models"
    assert captured[1]["authorization"] == "Bearer test-primary-token"
    assert captured[1]["content_type"] is None
    assert captured[1]["user_agent"] == "ai-inference-gateway/1.0"

    assert readiness["ready"] is True
