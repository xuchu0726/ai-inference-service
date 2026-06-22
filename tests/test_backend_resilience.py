import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
    UpstreamProtocolError,
)
from app.main import app
from app.metrics.prometheus_metrics import gateway_backend_failures_total


@pytest.mark.parametrize(
    ("error", "expected_status", "error_type"),
    [
        (
            BackendUnavailableError("vLLM server is unreachable"),
            503,
            "backend_unavailable",
        ),
        (
            BackendTimeoutError("vLLM request timed out"),
            504,
            "backend_timeout",
        ),
        (
            UpstreamProtocolError("vLLM returned invalid JSON"),
            502,
            "upstream_protocol_error",
        ),
    ],
)
def test_generate_maps_backend_failures_to_stable_api_errors(
    monkeypatch,
    error,
    expected_status,
    error_type,
):
    def raise_backend_error(**_kwargs):
        raise error

    monkeypatch.setattr(main_module, "generate_text", raise_backend_error)

    before = gateway_backend_failures_total.labels(
        backend="mock",
        error_type=error_type,
    )._value.get()

    response = TestClient(app).post(
        "/generate",
        json={
            "prompt": "backend failure classification test",
            "max_new_tokens": 8,
            "temperature": 0.0,
        },
    )

    after = gateway_backend_failures_total.labels(
        backend="mock",
        error_type=error_type,
    )._value.get()

    assert response.status_code == expected_status
    assert response.json()["detail"]["error"] == error_type
    assert response.json()["detail"]["backend"] == "mock"
    assert after == before + 1
