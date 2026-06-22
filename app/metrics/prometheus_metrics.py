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

gateway_backend_failures_total = Counter(
    "gateway_backend_failures_total",
    "Number of gateway backend failures.",
    ["backend", "error_type"],
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


def record_backend_failure(backend: str, error_type: str) -> None:
    gateway_backend_failures_total.labels(
        backend=backend,
        error_type=error_type,
    ).inc()

gateway_retry_attempts_total = Counter(
    "gateway_retry_attempts_total",
    "Number of bounded retry attempts issued by the gateway.",
    ["backend", "reason"],
)

gateway_circuit_breaker_state = Gauge(
    "gateway_circuit_breaker_state",
    "Current process-local circuit breaker state encoded as one-hot labels.",
    ["backend", "state"],
)

gateway_circuit_breaker_transitions_total = Counter(
    "gateway_circuit_breaker_transitions_total",
    "Number of circuit breaker state transitions.",
    ["backend", "from_state", "to_state"],
)

gateway_fallback_requests_total = Counter(
    "gateway_fallback_requests_total",
    "Number of low-budget fallback requests.",
    ["backend", "result"],
)

gateway_fallback_thinking_budget = Gauge(
    "gateway_fallback_thinking_budget",
    "Configured thinking budget used by the fallback route.",
    ["backend"],
)


def record_retry(backend: str, reason: str) -> None:
    gateway_retry_attempts_total.labels(
        backend=backend,
        reason=reason,
    ).inc()


def record_circuit_state(backend: str, state: str) -> None:
    for candidate in ("closed", "open", "half_open"):
        gateway_circuit_breaker_state.labels(
            backend=backend,
            state=candidate,
        ).set(1 if candidate == state else 0)


def record_circuit_transition(
    backend: str,
    from_state: str,
    to_state: str,
) -> None:
    gateway_circuit_breaker_transitions_total.labels(
        backend=backend,
        from_state=from_state,
        to_state=to_state,
    ).inc()


def record_fallback(
    backend: str,
    result: str,
    thinking_budget: int,
) -> None:
    gateway_fallback_requests_total.labels(
        backend=backend,
        result=result,
    ).inc()

    gateway_fallback_thinking_budget.labels(
        backend=backend,
    ).set(thinking_budget)
