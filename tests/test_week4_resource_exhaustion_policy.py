from __future__ import annotations

from io import BytesIO
import urllib.error
import urllib.request

import pytest

from app.backends.errors import BackendResourceExhaustedError
from app.backends.vllm_backend import VLLMBackend
from app.resilience import CircuitBreaker, ResilienceController


def test_vllm_http_500_cuda_oom_maps_to_resource_exhausted(monkeypatch) -> None:
    backend = VLLMBackend(
        base_url="http://primary.example/v1",
        model_name="Seed-OSS-36B-Instruct-W8A8",
        timeout_seconds=10,
    )

    http_error = urllib.error.HTTPError(
        url="http://primary.example/v1/chat/completions",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=BytesIO(
            b'{"error":{"message":"CUDA out of memory while allocating KV cache"}}'
        ),
    )

    def raise_http_error(*args, **kwargs):
        raise http_error

    monkeypatch.setattr(urllib.request, "urlopen", raise_http_error)

    with pytest.raises(BackendResourceExhaustedError) as exc_info:
        backend.generate(prompt="trigger controlled OOM", max_new_tokens=8)

    assert "resource exhausted" in str(exc_info.value).lower()
    assert "out of memory" in str(exc_info.value).lower()


def test_resource_exhaustion_bypasses_retry_and_uses_fallback() -> None:
    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=10,
        ),
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    calls = {"primary": 0, "fallback": 0}

    def primary():
        calls["primary"] += 1
        raise BackendResourceExhaustedError("CUDA out of memory")

    def fallback():
        calls["fallback"] += 1
        return {"response": "fallback answer"}

    outcome = controller.execute(
        request_id="resource-exhaustion-test",
        primary_operation=primary,
        fallback_operation=fallback,
        fallback_budget=512,
        is_retry_safe=lambda error: False,
        is_fallback_safe=lambda error: isinstance(
            error,
            BackendResourceExhaustedError,
        ),
    )

    assert outcome.route == "fallback"
    assert outcome.primary_attempts == 1
    assert outcome.fallback_budget == 512
    assert calls == {"primary": 1, "fallback": 1}
