import json
import time
import urllib.error
import urllib.request


class VLLMBackend:
    """
    Backend that calls a vLLM OpenAI-compatible server.

    This backend does not load the model inside the FastAPI process.
    Instead, it sends HTTP requests to a separate vLLM server process,
    which is closer to a real LLM serving architecture.
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        thinking_budget: int | None = None,
    ) -> dict:
        start_time = time.time()

        # vLLM exposes an OpenAI-compatible chat completions API.
        # For models that support thinking control natively, this field may need
        # model-specific handling later. For now, we pass it through as metadata
        # in our own API response and keep max_new_tokens as the actual generation cap.
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens": max_new_tokens,
            "temperature": temperature,
        }

        request_body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")
                data = json.loads(raw_body)

        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"vLLM request failed with HTTP {exc.code}: {error_body}"
            ) from exc

        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"vLLM server is not reachable at {self.base_url}: {exc}"
            ) from exc

        latency_seconds = time.time() - start_time

        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"vLLM response has no choices: {data}")

        message = choices[0].get("message", {})
        response_text = message.get("content", "")

        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")

        tokens_per_second = None
        if output_tokens is not None and latency_seconds > 0:
            tokens_per_second = output_tokens / latency_seconds

        return {
            "response": response_text,
            "latency_seconds": round(latency_seconds, 6),
            "input_chars": len(prompt),
            "max_new_tokens": max_new_tokens,
            "thinking_budget": thinking_budget,
            "backend": "vllm",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tokens_per_second": round(tokens_per_second, 4)
            if tokens_per_second is not None
            else None,
            "model_name": self.model_name,
            "device": "vllm_server",
            "total_tokens": total_tokens,
        }
