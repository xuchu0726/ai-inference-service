from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
)
from app.backends.mock_backend import MockBackend
from app.backends.vllm_backend import VLLMBackend
from app.config import (
    INFERENCE_BACKEND,
    MODEL_NAME,
    RESILIENCE_FAILURE_THRESHOLD,
    RESILIENCE_FALLBACK_THINKING_BUDGET,
    RESILIENCE_RECOVERY_TIMEOUT_SECONDS,
    RESILIENCE_RETRY_ATTEMPTS,
    RESILIENCE_RETRY_BACKOFF_SECONDS,
    TRANSFORMERS_DEFAULT_THINKING_BUDGET,
    TRANSFORMERS_DEVICE_MAP,
    TRANSFORMERS_LOAD_IN_8BIT,
    VLLM_BASE_URL,
    VLLM_ENABLE_SEED_THINKING_BUDGET,
    VLLM_FALLBACK_BASE_URL,
    VLLM_FALLBACK_MODEL_NAME,
    VLLM_MODEL_NAME,
    VLLM_TIMEOUT_SECONDS,
)
from app.metrics.prometheus_metrics import (
    record_circuit_state,
    record_circuit_transition,
    record_fallback,
    record_retry,
)
from app.resilience import (
    CircuitBreaker,
    ResilienceController,
    new_request_id,
)


def _build_backend():
    if INFERENCE_BACKEND == "transformers":
        from app.backends.transformers_backend import TransformersBackend

        return TransformersBackend(
            model_name=MODEL_NAME,
            load_in_8bit=TRANSFORMERS_LOAD_IN_8BIT,
            device_map=TRANSFORMERS_DEVICE_MAP,
            default_thinking_budget=TRANSFORMERS_DEFAULT_THINKING_BUDGET,
        )

    if INFERENCE_BACKEND == "vllm":
        return VLLMBackend(
            base_url=VLLM_BASE_URL,
            model_name=VLLM_MODEL_NAME,
            timeout_seconds=VLLM_TIMEOUT_SECONDS,
            enable_seed_thinking_budget=VLLM_ENABLE_SEED_THINKING_BUDGET,
        )

    if INFERENCE_BACKEND == "mock":
        return MockBackend()

    raise ValueError(f"Unsupported INFERENCE_BACKEND: {INFERENCE_BACKEND}")


def _build_fallback_backend():
    if INFERENCE_BACKEND != "vllm" or not VLLM_FALLBACK_BASE_URL:
        return None

    if VLLM_FALLBACK_BASE_URL == VLLM_BASE_URL:
        raise ValueError(
            "VLLM_FALLBACK_BASE_URL must be different from VLLM_BASE_URL"
        )

    return VLLMBackend(
        base_url=VLLM_FALLBACK_BASE_URL,
        model_name=VLLM_FALLBACK_MODEL_NAME,
        timeout_seconds=VLLM_TIMEOUT_SECONDS,
        enable_seed_thinking_budget=VLLM_ENABLE_SEED_THINKING_BUDGET,
    )


backend = _build_backend()
fallback_backend = _build_fallback_backend()

circuit_breaker = CircuitBreaker(
    failure_threshold=RESILIENCE_FAILURE_THRESHOLD,
    recovery_timeout_seconds=RESILIENCE_RECOVERY_TIMEOUT_SECONDS,
)

resilience_controller = ResilienceController(
    breaker=circuit_breaker,
    retry_attempts=RESILIENCE_RETRY_ATTEMPTS,
    retry_backoff_seconds=RESILIENCE_RETRY_BACKOFF_SECONDS,
)


def _backend_name() -> str:
    return INFERENCE_BACKEND


def _is_retry_safe(error: Exception) -> bool:
    return isinstance(
        error,
        (BackendUnavailableError, BackendTimeoutError),
    )


def _is_fallback_safe(error: Exception) -> bool:
    return isinstance(
        error,
        (BackendUnavailableError, BackendTimeoutError),
    )


def generate_text(
    prompt: str,
    max_new_tokens: int = 128,
    temperature: float = 0.7,
    thinking_budget: int | None = None,
):
    request_id = new_request_id()

    def primary_operation():
        return backend.generate(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            thinking_budget=thinking_budget,
        )

    fallback_budget = RESILIENCE_FALLBACK_THINKING_BUDGET

    def fallback_operation():
        if fallback_backend is None:
            raise RuntimeError("fallback backend is not configured")

        return fallback_backend.generate(
            prompt=prompt,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            thinking_budget=fallback_budget,
        )

    def on_retry(error: Exception) -> None:
        if isinstance(error, BackendTimeoutError):
            reason = "backend_timeout"
        elif isinstance(error, BackendUnavailableError):
            reason = "backend_unavailable"
        else:
            reason = "unknown"

        record_retry(
            backend=_backend_name(),
            reason=reason,
        )

    def on_transition(transition) -> None:
        record_circuit_transition(
            backend=_backend_name(),
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
        )

    def on_fallback(result: str) -> None:
        record_fallback(
            backend=_backend_name(),
            result=result,
            thinking_budget=fallback_budget,
        )

    record_circuit_state(
        backend=_backend_name(),
        state=resilience_controller.breaker.state.value,
    )

    outcome = resilience_controller.execute(
        request_id=request_id,
        primary_operation=primary_operation,
        fallback_operation=(
            fallback_operation
            if fallback_backend is not None
            else None
        ),
        fallback_budget=(
            fallback_budget
            if fallback_backend is not None
            else None
        ),
        is_retry_safe=_is_retry_safe,
        is_fallback_safe=_is_fallback_safe,
        on_retry=on_retry,
        on_transition=on_transition,
        on_fallback=on_fallback,
    )

    record_circuit_state(
        backend=_backend_name(),
        state=resilience_controller.breaker.state.value,
    )

    result = dict(outcome.value)
    result.update(
        {
            "request_id": outcome.request_id,
            "route": outcome.route,
            "primary_attempts": outcome.primary_attempts,
            "fallback_thinking_budget": outcome.fallback_budget,
        }
    )
    return result
