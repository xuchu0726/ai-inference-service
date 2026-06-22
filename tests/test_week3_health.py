from fastapi.testclient import TestClient

from app.main import app
import app.main as main_module


class ReadyBackend:
    def check_ready(self):
        return {
            "ready": True,
            "backend": "test-ready",
            "detail": "test backend is available",
        }


class UnreadyBackend:
    def check_ready(self):
        return {
            "ready": False,
            "backend": "test-unready",
            "detail": "simulated backend outage",
        }


def test_livez_does_not_depend_on_backend(monkeypatch):
    monkeypatch.setattr(main_module, "backend", UnreadyBackend())

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert response.json()["status"] == "live"


def test_readyz_and_health_are_healthy_when_backend_is_ready(monkeypatch):
    monkeypatch.setattr(main_module, "backend", ReadyBackend())
    client = TestClient(app)

    ready_response = client.get("/readyz")
    health_response = client.get("/health")

    assert ready_response.status_code == 200
    assert ready_response.json()["status"] == "ready"
    assert ready_response.json()["backend"] == "test-ready"

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert health_response.json()["backend"] == "test-ready"


def test_readyz_and_health_are_degraded_when_backend_is_unready(monkeypatch):
    monkeypatch.setattr(main_module, "backend", UnreadyBackend())
    client = TestClient(app)

    ready_response = client.get("/readyz")
    health_response = client.get("/health")

    assert ready_response.status_code == 503
    assert ready_response.json()["detail"]["backend"] == "test-unready"

    assert health_response.status_code == 503
    assert health_response.json()["detail"]["status"] == "degraded"
    assert health_response.json()["detail"]["backend"] == "test-unready"


def test_gateway_instance_header_uses_environment(monkeypatch):
    monkeypatch.setenv("POD_NAME", "gateway-test-instance")

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert response.headers["X-Gateway-Instance"] == "gateway-test-instance"


def test_mock_cpu_burn_can_be_disabled(monkeypatch):
    monkeypatch.setattr("app.backends.mock_backend.MOCK_CPU_BURN_MS", 0)

    from app.backends.mock_backend import MockBackend

    result = MockBackend().generate("cpu burn disabled")

    assert result["backend"] == "mock"
    assert result["latency_seconds"] >= 0
