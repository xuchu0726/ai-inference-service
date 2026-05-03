from app.backends.mock_backend import MockBackend
from app.backends.transformers_backend import TransformersBackend
from app.config import INFERENCE_BACKEND, MODEL_NAME


if INFERENCE_BACKEND == "transformers":
    backend = TransformersBackend(model_name=MODEL_NAME)
elif INFERENCE_BACKEND == "mock":
    backend = MockBackend()
else:
    raise ValueError(f"Unsupported INFERENCE_BACKEND: {INFERENCE_BACKEND}")


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
