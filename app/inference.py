from app.backends.mock_backend import MockBackend
from app.backends.vllm_backend import VLLMBackend
from app.config import (
    INFERENCE_BACKEND,
    MODEL_NAME,
    VLLM_BASE_URL,
    VLLM_MODEL_NAME,
    VLLM_TIMEOUT_SECONDS,
    VLLM_ENABLE_SEED_THINKING_BUDGET,
    TRANSFORMERS_LOAD_IN_8BIT,
    TRANSFORMERS_DEVICE_MAP,
    TRANSFORMERS_DEFAULT_THINKING_BUDGET,
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


backend = _build_backend()


def generate_text(
    prompt: str,
    max_new_tokens: int = 128,
    temperature: float = 0.7,
    thinking_budget: int | None = None,
):
    return backend.generate(
        prompt=prompt,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        thinking_budget=thinking_budget,
    )
