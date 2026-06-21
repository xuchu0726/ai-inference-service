from prometheus_client import Counter, Gauge


gateway_backend_ready = Gauge(
    "gateway_backend_ready",
    "Whether the configured inference backend is ready.",
    ["backend"],
)

gateway_readiness_checks_total = Counter(
    "gateway_readiness_checks_total",
    "Number of backend readiness checks.",
    ["backend", "result"],
)


def record_backend_readiness(status: dict) -> None:
    backend = status.get("backend", "unknown")
    ready = bool(status.get("ready", False))
    result = "ready" if ready else "not_ready"

    gateway_backend_ready.labels(backend=backend).set(1 if ready else 0)
    gateway_readiness_checks_total.labels(
        backend=backend,
        result=result,
    ).inc()
