from pydantic import BaseModel
from typing import Optional


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