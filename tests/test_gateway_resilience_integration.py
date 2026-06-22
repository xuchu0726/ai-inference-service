from fastapi.testclient import TestClient

import app.inference as inference_module
import app.main as main_module
from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
)
from app.main import app
from app.resilience import (
    CircuitBreaker,
    ResilienceController,
)


def _reset_resilience(
    monkeypatch,
    *,
    failure_threshold=3,
    retry_attempts=1,
):
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout_seconds=60,
    )
    controller = ResilienceController(
        breaker=breaker,
        retry_attempts=retry_attempts,
        retry_backoff_seconds=0,
    )
    monkeypatch.setattr(inference_module, "resilience_controller", controller)
    return controller


def test_generate_retries_backend_unavailable_once(monkeypatch):
    _reset_resilience(monkeypatch)

    retry_events = []
    monkeypatch.setattr(
        inference_module,
        "record_retry",
        lambda **kwargs: retry_events.append(kwargs),
    )

    calls = {"count": 0}

    class FlakyBackend:
        def generate(self, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise BackendUnavailableError("temporary connection failure")

            return {
                "response": "ok",
                "latency_seconds": 0.01,
                "input_chars": 4,
                "max_new_tokens": 8,
                "thinking_budget": None,
                "backend": "mock",
            }

    monkeypatch.setattr(inference_module, "backend", FlakyBackend())
    monkeypatch.setattr(inference_module, "fallback_backend", None)

    response = TestClient(app).post(
        "/generate",
        json={
            "prompt": "ping",
            "max_new_tokens": 8,
            "temperature": 0.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["route"] == "primary"
    assert response.json()["primary_attempts"] == 2
    assert response.headers["X-Inference-Route"] == "primary"
    assert response.headers["X-Request-ID"]
    assert calls["count"] == 2
    assert retry_events == [
        {"backend": "mock", "reason": "backend_unavailable"}
    ]


def test_generate_retries_backend_timeout_once(monkeypatch):
    _reset_resilience(monkeypatch)

    retry_events = []
    monkeypatch.setattr(
        inference_module,
        "record_retry",
        lambda **kwargs: retry_events.append(kwargs),
    )

    calls = {"count": 0}

    class TimeoutThenSuccessBackend:
        def generate(self, **_kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise BackendTimeoutError("simulated timeout")

            return {
                "response": "ok",
                "latency_seconds": 0.01,
                "input_chars": 4,
                "max_new_tokens": 8,
                "thinking_budget": None,
                "backend": "mock",
            }

    monkeypatch.setattr(
        inference_module,
        "backend",
        TimeoutThenSuccessBackend(),
    )
    monkeypatch.setattr(inference_module, "fallback_backend", None)

    response = TestClient(app).post(
        "/generate",
        json={
            "prompt": "timeout",
            "max_new_tokens": 8,
            "temperature": 0.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["route"] == "primary"
    assert response.json()["primary_attempts"] == 2
    assert calls["count"] == 2
    assert retry_events == [
        {"backend": "mock", "reason": "backend_timeout"}
    ]


def test_generate_returns_circuit_open_when_no_fallback(monkeypatch):
    _reset_resilience(
        monkeypatch,
        failure_threshold=1,
        retry_attempts=0,
    )

    class DownBackend:
        def generate(self, **_kwargs):
            raise BackendUnavailableError("primary unavailable")

    monkeypatch.setattr(inference_module, "backend", DownBackend())
    monkeypatch.setattr(inference_module, "fallback_backend", None)

    client = TestClient(app)

    first = client.post(
        "/generate",
        json={"prompt": "open breaker"},
    )
    second = client.post(
        "/generate",
        json={"prompt": "blocked"},
    )

    assert first.status_code == 503
    assert first.json()["detail"]["error"] == "backend_unavailable"

    assert second.status_code == 503
    assert second.json()["detail"]["error"] == "circuit_open"


def test_generate_uses_fallback_with_budget_512(monkeypatch):
    _reset_resilience(
        monkeypatch,
        failure_threshold=1,
        retry_attempts=0,
    )

    fallback_budgets = []

    class DownBackend:
        def generate(self, **_kwargs):
            raise BackendUnavailableError("primary unavailable")

    class FallbackBackend:
        def generate(self, **kwargs):
            fallback_budgets.append(kwargs["thinking_budget"])
            return {
                "response": "fallback answer",
                "latency_seconds": 0.02,
                "input_chars": len(kwargs["prompt"]),
                "max_new_tokens": kwargs["max_new_tokens"],
                "thinking_budget": kwargs["thinking_budget"],
                "backend": "fallback",
            }

    monkeypatch.setattr(inference_module, "backend", DownBackend())
    monkeypatch.setattr(
        inference_module,
        "fallback_backend",
        FallbackBackend(),
    )

    response = TestClient(app).post(
        "/generate",
        json={
            "prompt": "fallback test",
            "thinking_budget": 1024,
            "max_new_tokens": 8,
            "temperature": 0.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["route"] == "fallback"
    assert response.json()["fallback_thinking_budget"] == 512
    assert response.json()["thinking_budget"] == 512
    assert fallback_budgets == [512]
