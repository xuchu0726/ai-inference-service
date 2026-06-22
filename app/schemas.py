from typing import Optional

from pydantic import BaseModel


class GenerateRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 128
    temperature: float = 0.7
    thinking_budget: Optional[int] = None


class GenerateResponse(BaseModel):
    response: str
    latency_seconds: float
    input_chars: int
    max_new_tokens: int
    thinking_budget: Optional[int] = None
    backend: str

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    tokens_per_second: Optional[float] = None
    model_name: Optional[str] = None
    device: Optional[str] = None
    total_tokens: Optional[int] = None

    request_id: Optional[str] = None
    route: Optional[str] = None
    primary_attempts: Optional[int] = None
    fallback_thinking_budget: Optional[int] = None
