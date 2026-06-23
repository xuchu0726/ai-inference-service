import json
import socket
import time
import urllib.error
import urllib.request

from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
    UpstreamProtocolError,
)


class VLLMBackend:
    """
    调用 vLLM OpenAI-compatible 服务的后端。

    该后端不在 FastAPI 进程内加载模型，而是向独立的 vLLM 服务进程发送 HTTP 请求。
    """

    def __init__(
        self,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 300,
        enable_seed_thinking_budget: bool = False,
        api_key: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.enable_seed_thinking_budget = enable_seed_thinking_budget
        self.api_key = api_key

    def _headers(self, *, include_content_type: bool = False) -> dict:
        headers = {
            "User-Agent": "ai-inference-gateway/1.0",
        }

        if include_content_type:
            headers["Content-Type"] = "application/json"

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        return headers

    def _should_use_seed_thinking_budget(self) -> bool:
        return self.enable_seed_thinking_budget or "Seed-OSS" in self.model_name

    def _normalize_seed_thinking_budget(self, thinking_budget: int | None) -> int | None:
        if thinking_budget is None:
            return None

        # Seed-OSS 的 thinking budget 通过模型 chat template 生效。
        # 非零且低于 512 的预算统一归零，避免使用未覆盖的低预算配置。
        if 0 < thinking_budget < 512:
            return 0

        return thinking_budget

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 128,
        temperature: float = 0.7,
        thinking_budget: int | None = None,
    ) -> dict:
        start_time = time.time()

        # vLLM 提供 OpenAI-compatible chat completions API。
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

        # Seed-OSS 通过 chat_template_kwargs 控制原生 thinking budget。
        # 通用模型和 Qwen 模型不发送该字段，避免兼容性问题。
        if self._should_use_seed_thinking_budget():
            normalized_budget = self._normalize_seed_thinking_budget(thinking_budget)
            if normalized_budget is not None:
                payload["chat_template_kwargs"] = {
                    "thinking_budget": normalized_budget,
                }

        request_body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=request_body,
            headers=self._headers(include_content_type=True),
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
            raise UpstreamProtocolError(
                f"vLLM returned HTTP {exc.code}"
            ) from exc

        except (TimeoutError, socket.timeout) as exc:
            raise BackendTimeoutError(
                f"vLLM request timed out after {self.timeout_seconds}s"
            ) from exc

        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise BackendTimeoutError(
                    f"vLLM request timed out after {self.timeout_seconds}s"
                ) from exc

            raise BackendUnavailableError(
                f"vLLM server is unreachable at {self.base_url}"
            ) from exc

        except json.JSONDecodeError as exc:
            raise UpstreamProtocolError(
                "vLLM returned invalid JSON"
            ) from exc

        latency_seconds = time.time() - start_time

        choices = data.get("choices", [])
        if not choices:
            raise UpstreamProtocolError(
                "vLLM response contains no choices"
            )

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


    def check_ready(self) -> dict:
        request = urllib.request.Request(
            url=f"{self.base_url}/models",
            method="GET",
            headers=self._headers(),
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=min(self.timeout_seconds, 10),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))

            return {
                "ready": True,
                "backend": "vllm",
                "model_name": self.model_name,
                "models": len(payload.get("data", [])),
            }

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            return {
                "ready": False,
                "backend": "vllm",
                "model_name": self.model_name,
                "detail": str(exc),
            }
