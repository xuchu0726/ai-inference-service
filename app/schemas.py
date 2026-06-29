from typing import Literal, Optional

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

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    created_at_ms: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at_ms: int
    updated_at_ms: int
    attempt_count: int = 0
    worker: Optional[str] = None
    result: Optional[GenerateResponse] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
