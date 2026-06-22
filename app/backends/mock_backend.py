import os
import time

from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
)
from app.config import MOCK_CPU_BURN_MS


def _burn_cpu(milliseconds: int) -> None:
    if milliseconds <= 0:
        return

    deadline = time.perf_counter() + milliseconds / 1000.0
    value = 0

    while time.perf_counter() < deadline:
        value = (value * 31 + 17) % 1_000_003

    if value == -1:
        raise RuntimeError("unreachable")


class MockBackend:
    def __init__(self) -> None:
        raw_sequence = os.getenv("MOCK_FAILURE_SEQUENCE", "").strip()
        self._failure_sequence = [
            item.strip()
            for item in raw_sequence.split(",")
            if item.strip()
        ]
        self._calls = 0

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        thinking_budget: int | None = None,
    ) -> dict:
        start = time.time()
        self._calls += 1

        if self._calls <= len(self._failure_sequence):
            failure = self._failure_sequence[self._calls - 1]

            if failure == "unavailable":
                raise BackendUnavailableError(
                    f"mock backend unavailable on call {self._calls}"
                )

            if failure == "timeout":
                raise BackendTimeoutError(
                    f"mock backend timeout on call {self._calls}"
                )

            if failure != "success":
                raise ValueError(
                    "MOCK_FAILURE_SEQUENCE only supports: "
                    "success, unavailable, timeout"
                )

        _burn_cpu(MOCK_CPU_BURN_MS)

        response = (
            f"[Mock Output] Received prompt with {len(prompt)} characters. "
            f"max_new_tokens={max_new_tokens}, "
            f"temperature={temperature}, "
            f"thinking_budget={thinking_budget}."
        )

        latency = time.time() - start

        return {
            "response": response,
            "latency_seconds": latency,
            "input_chars": len(prompt),
            "max_new_tokens": max_new_tokens,
            "thinking_budget": thinking_budget,
            "backend": "mock",
        }


    def check_ready(self) -> dict:
        return {
            "ready": True,
            "backend": "mock",
            "detail": "mock backend is available",
        }
