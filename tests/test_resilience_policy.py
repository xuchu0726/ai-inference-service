from app.backends.errors import BackendTimeoutError, BackendUnavailableError
from app.resilience import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ResilienceController,
)


def test_unavailable_retries_once_then_succeeds():
    calls = {"count": 0}
    retries = []

    def primary():
        calls["count"] += 1
        if calls["count"] == 1:
            raise BackendUnavailableError("temporary connection failure")
        return {"ok": True}

    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=3,
            recovery_timeout_seconds=20,
        ),
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    result = controller.execute(
        request_id="retry-once",
        primary_operation=primary,
        fallback_operation=None,
        fallback_budget=None,
        is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
        is_fallback_safe=lambda exc: False,
        on_retry=lambda reason: retries.append(reason),
    )

    assert result.route == "primary"
    assert result.primary_attempts == 2
    assert calls["count"] == 2
    assert len(retries) == 1
    assert isinstance(retries[0], BackendUnavailableError)
    assert controller.breaker.state == CircuitState.CLOSED


def test_timeout_is_not_retried():
    calls = {"count": 0}

    def primary():
        calls["count"] += 1
        raise BackendTimeoutError("generation timeout")

    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=3,
            recovery_timeout_seconds=20,
        ),
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    try:
        controller.execute(
            request_id="timeout-no-retry",
            primary_operation=primary,
            fallback_operation=None,
            fallback_budget=None,
            is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
            is_fallback_safe=lambda exc: False,
        )
    except BackendTimeoutError:
        pass
    else:
        raise AssertionError("BackendTimeoutError must propagate")

    assert calls["count"] == 1


def test_breaker_opens_after_three_primary_failures():
    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=3,
            recovery_timeout_seconds=60,
        ),
        retry_attempts=0,
        retry_backoff_seconds=0,
    )

    def primary():
        raise BackendUnavailableError("primary unavailable")

    for index in range(3):
        try:
            controller.execute(
                request_id=f"failure-{index}",
                primary_operation=primary,
                fallback_operation=None,
                fallback_budget=None,
                is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
                is_fallback_safe=lambda exc: False,
            )
        except BackendUnavailableError:
            pass

    assert controller.breaker.state == CircuitState.OPEN

    try:
        controller.execute(
            request_id="blocked-by-open-breaker",
            primary_operation=primary,
            fallback_operation=None,
            fallback_budget=None,
            is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
            is_fallback_safe=lambda exc: False,
        )
    except CircuitOpenError:
        pass
    else:
        raise AssertionError("open breaker must block the primary route")


def test_open_breaker_uses_fallback_budget_512():
    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=60,
        ),
        retry_attempts=0,
        retry_backoff_seconds=0,
    )

    def primary():
        raise BackendUnavailableError("primary unavailable")

    try:
        controller.execute(
            request_id="open-breaker",
            primary_operation=primary,
            fallback_operation=None,
            fallback_budget=None,
            is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
            is_fallback_safe=lambda exc: False,
        )
    except BackendUnavailableError:
        pass

    fallback_budgets = []

    def fallback():
        fallback_budgets.append(512)
        return {"backend": "fallback"}

    result = controller.execute(
        request_id="fallback-request",
        primary_operation=primary,
        fallback_operation=fallback,
        fallback_budget=512,
        is_retry_safe=lambda exc: isinstance(exc, BackendUnavailableError),
        is_fallback_safe=lambda exc: isinstance(
            exc,
            (BackendUnavailableError, BackendTimeoutError),
        ),
    )

    assert result.route == "fallback"
    assert result.primary_attempts == 0
    assert result.fallback_budget == 512
    assert fallback_budgets == [512]


def test_half_open_success_closes_breaker():
    now = {"value": 0.0}

    def clock():
        return now["value"]

    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=10,
        clock=clock,
    )

    controller = ResilienceController(
        breaker=breaker,
        retry_attempts=0,
        retry_backoff_seconds=0,
    )

    def failed_primary():
        raise BackendUnavailableError("primary unavailable")

    try:
        controller.execute(
            request_id="open",
            primary_operation=failed_primary,
            fallback_operation=None,
            fallback_budget=None,
            is_retry_safe=lambda exc: False,
            is_fallback_safe=lambda exc: False,
        )
    except BackendUnavailableError:
        pass

    assert breaker.state == CircuitState.OPEN

    now["value"] = 10.0

    result = controller.execute(
        request_id="half-open-success",
        primary_operation=lambda: {"ok": True},
        fallback_operation=None,
        fallback_budget=None,
        is_retry_safe=lambda exc: False,
        is_fallback_safe=lambda exc: False,
    )

    assert result.route == "primary"
    assert breaker.state == CircuitState.CLOSED


def test_timeout_is_retry_safe():
    from app.inference import _is_retry_safe

    assert _is_retry_safe(BackendTimeoutError("simulated timeout"))


def test_timeout_retry_callback_receives_timeout_error():
    calls = {"count": 0}
    retries = []

    def primary():
        calls["count"] += 1
        if calls["count"] == 1:
            raise BackendTimeoutError("simulated timeout")
        return {"ok": True}

    controller = ResilienceController(
        breaker=CircuitBreaker(
            failure_threshold=3,
            recovery_timeout_seconds=20,
        ),
        retry_attempts=1,
        retry_backoff_seconds=0,
    )

    result = controller.execute(
        request_id="timeout-retry-once",
        primary_operation=primary,
        fallback_operation=None,
        fallback_budget=None,
        is_retry_safe=lambda exc: isinstance(
            exc,
            (BackendUnavailableError, BackendTimeoutError),
        ),
        is_fallback_safe=lambda exc: False,
        on_retry=lambda error: retries.append(error),
    )

    assert result.route == "primary"
    assert result.primary_attempts == 2
    assert calls["count"] == 2
    assert len(retries) == 1
    assert isinstance(retries[0], BackendTimeoutError)
