from fastapi.testclient import TestClient

import app.main as main


class ReadyBackend:
    def __init__(self, ready: bool, name: str):
        self.ready = ready
        self.name = name

    def check_ready(self):
        return {
            "ready": self.ready,
            "backend": self.name,
        }


def test_readyz_stays_ready_when_primary_is_down_but_fallback_is_ready(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "backend",
        ReadyBackend(False, "primary-vllm"),
    )
    monkeypatch.setattr(
        main,
        "fallback_backend",
        ReadyBackend(True, "fallback-vllm"),
    )

    client = TestClient(main.app)
    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()

    assert payload["ready"] is True
    assert payload["primary"]["ready"] is False
    assert payload["fallback"]["ready"] is True


def test_readyz_is_unready_when_primary_and_fallback_are_both_down(
    monkeypatch,
):
    monkeypatch.setattr(
        main,
        "backend",
        ReadyBackend(False, "primary-vllm"),
    )
    monkeypatch.setattr(
        main,
        "fallback_backend",
        ReadyBackend(False, "fallback-vllm"),
    )

    client = TestClient(main.app)
    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.json()["detail"]

    assert payload["primary"]["ready"] is False
    assert payload["fallback"]["ready"] is False
