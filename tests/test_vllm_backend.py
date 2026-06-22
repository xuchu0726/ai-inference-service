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
