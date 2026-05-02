from typing import Protocol


class InferenceBackend(Protocol):
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        thinking_budget: int | None = None,
    ) -> dict:
        ...
