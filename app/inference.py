from app.backends.mock_backend import MockBackend

backend = MockBackend()


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
