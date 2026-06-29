from app import job_worker


def test_worker_metrics_server_uses_requested_host_and_port(monkeypatch):
    calls = []

    def fake_start_http_server(port, addr):
        calls.append((port, addr))

    monkeypatch.setattr(
        job_worker,
        "start_http_server",
        fake_start_http_server,
    )

    job_worker.start_worker_metrics_server(
        host="127.0.0.1",
        port=19101,
    )

    assert calls == [(19101, "127.0.0.1")]
