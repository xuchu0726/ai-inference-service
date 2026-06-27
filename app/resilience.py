from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Protocol, TypeVar


T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    def __init__(self, retry_after_seconds: float):
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(
            "primary upstream circuit is open; "
            f"retry after {self.retry_after_seconds:.3f}s"
        )


@dataclass(frozen=True)
class CircuitTransition:
    from_state: CircuitState
    to_state: CircuitState


@dataclass(frozen=True)
class CircuitPermit:
    state: CircuitState
    version: int | None = None
    probe_token: str | None = None
    store: str = "local"


class CircuitBreakerProtocol(Protocol):
    @property
    def state(self) -> CircuitState: ...

    def allow_primary_call(self) -> CircuitPermit: ...

    def record_success(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None: ...

    def record_failure(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None: ...

    def snapshot(self) -> dict[str, float | int | str]: ...


@dataclass(frozen=True)
class ResilienceOutcome(Generic[T]):
    value: T
    route: str
    request_id: str
    primary_attempts: int
    circuit_state: CircuitState
    fallback_budget: int | None = None


def new_request_id() -> str:
    return uuid.uuid4().hex


class CircuitBreaker:
    """
    Process-local circuit breaker.

    Each Gateway Pod owns one breaker instance. State is intentionally not
    shared across Pods because the current local deployment has no durable,
    cluster-wide state store.
    """

    def __init__(
        self,
        failure_threshold: int,
        recovery_timeout_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")

        if recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be positive")

        self._failure_threshold = failure_threshold
        self._recovery_timeout_seconds = recovery_timeout_seconds
        self._clock = clock

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        with self._lock:
            self._advance_open_state_if_ready()
            return self._state

    def allow_primary_call(self) -> CircuitPermit:
        with self._lock:
            self._advance_open_state_if_ready()

            if self._state == CircuitState.OPEN:
                raise CircuitOpenError(self._remaining_open_seconds())

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    raise CircuitOpenError(self._remaining_open_seconds())

                self._half_open_probe_in_flight = True

            return CircuitPermit(state=self._state)

    def record_success(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None:
        with self._lock:
            previous = self._state
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
            self._half_open_probe_in_flight = False

            if previous != CircuitState.CLOSED:
                return CircuitTransition(previous, CircuitState.CLOSED)

            return None

    def record_failure(
        self,
        permit: CircuitPermit | None = None,
    ) -> CircuitTransition | None:
        with self._lock:
            previous = self._state
            self._half_open_probe_in_flight = False

            if previous == CircuitState.HALF_OPEN:
                self._open()
                return CircuitTransition(
                    CircuitState.HALF_OPEN,
                    CircuitState.OPEN,
                )

            self._consecutive_failures += 1

            if self._consecutive_failures >= self._failure_threshold:
                self._open()

                if previous != CircuitState.OPEN:
                    return CircuitTransition(previous, CircuitState.OPEN)

            return None

    def snapshot(self) -> dict[str, float | int | str]:
        with self._lock:
            self._advance_open_state_if_ready()

            return {
                "state": self._state.value,
                "consecutive_failures": self._consecutive_failures,
                "retry_after_seconds": round(self._remaining_open_seconds(), 6),
            }

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()

    def _advance_open_state_if_ready(self) -> None:
        if self._state != CircuitState.OPEN:
            return

        if self._remaining_open_seconds() > 0:
            return

        self._state = CircuitState.HALF_OPEN
        self._half_open_probe_in_flight = False

    def _remaining_open_seconds(self) -> float:
        if self._opened_at is None:
            return 0.0

        elapsed = self._clock() - self._opened_at
        return max(0.0, self._recovery_timeout_seconds - elapsed)


class ResilienceController:
    """
    Applies bounded retry, circuit breaking, and an optional fallback route.

    Retry and fallback are caller-controlled through predicates because a
    generation request must not be replayed after an ambiguous timeout.
    """

    def __init__(
        self,
        breaker: CircuitBreakerProtocol,
        retry_attempts: int,
        retry_backoff_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if retry_attempts < 0:
            raise ValueError("retry_attempts must not be negative")

        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must not be negative")

        self._breaker = breaker
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._sleep = sleep

    @property
    def breaker(self) -> CircuitBreakerProtocol:
        return self._breaker

    def execute(
        self,
        *,
        request_id: str,
        primary_operation: Callable[[], T],
        fallback_operation: Callable[[], T] | None,
        fallback_budget: int | None,
        is_retry_safe: Callable[[Exception], bool],
        is_fallback_safe: Callable[[Exception], bool],
        on_retry: Callable[[Exception], None] | None = None,
        on_transition: Callable[[CircuitTransition], None] | None = None,
        on_fallback: Callable[[str], None] | None = None,
    ) -> ResilienceOutcome[T]:
        try:
            permit = self._breaker.allow_primary_call()
            state_before_primary = permit.state
        except CircuitOpenError:
            return self._run_fallback_or_raise(
                request_id=request_id,
                fallback_operation=fallback_operation,
                fallback_budget=fallback_budget,
                on_fallback=on_fallback,
            )

        primary_attempts = 0

        while True:
            primary_attempts += 1

            try:
                value = primary_operation()
            except Exception as exc:
                retry_remaining = primary_attempts <= self._retry_attempts

                if retry_remaining and is_retry_safe(exc):
                    if on_retry is not None:
                        on_retry(exc)

                    if self._retry_backoff_seconds > 0:
                        self._sleep(self._retry_backoff_seconds)

                    continue

                transition = self._breaker.record_failure(permit)

                if transition is not None and on_transition is not None:
                    on_transition(transition)

                if fallback_operation is not None and is_fallback_safe(exc):
                    return self._run_fallback_or_raise(
                        request_id=request_id,
                        fallback_operation=fallback_operation,
                        fallback_budget=fallback_budget,
                        on_fallback=on_fallback,
                        primary_attempts=primary_attempts,
                    )

                raise

            else:
                transition = self._breaker.record_success(permit)

                if transition is not None and on_transition is not None:
                    on_transition(transition)

                return ResilienceOutcome(
                    value=value,
                    route="primary",
                    request_id=request_id,
                    primary_attempts=primary_attempts,
                    circuit_state=state_before_primary,
                )

    def _run_fallback_or_raise(
        self,
        *,
        request_id: str,
        fallback_operation: Callable[[], T] | None,
        fallback_budget: int | None,
        on_fallback: Callable[[str], None] | None,
        primary_attempts: int = 0,
    ) -> ResilienceOutcome[T]:
        if fallback_operation is None:
            raise CircuitOpenError(
                self._breaker.snapshot()["retry_after_seconds"]  # type: ignore[arg-type]
            )

        try:
            value = fallback_operation()
        except Exception:
            if on_fallback is not None:
                on_fallback("failed")
            raise

        if on_fallback is not None:
            on_fallback("succeeded")

        return ResilienceOutcome(
            value=value,
            route="fallback",
            request_id=request_id,
            primary_attempts=primary_attempts,
            circuit_state=self._breaker.state,
            fallback_budget=fallback_budget,
        )
