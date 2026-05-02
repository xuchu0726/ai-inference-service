import time


def generate_text(
    prompt: str,
    max_new_tokens: int = 128,
    temperature: float = 0.7,
    thinking_budget: int | None = None,
):
    start = time.time()

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
    }