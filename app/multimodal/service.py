import asyncio
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from urllib.error import URLError
from urllib.request import urlopen

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from gradio_client import Client, handle_file
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel

from app.multimodal.config import (
    BAGEL_BASE_URL,
    BAGEL_MAX_IMAGE_BYTES,
    BAGEL_MODEL_NAME,
    BAGEL_TIMEOUT_SECONDS,
)

router = APIRouter(prefix="/multimodal", tags=["multimodal"])

multimodal_requests_total = Counter(
    "multimodal_requests_total",
    "Number of multimodal requests handled by the BAGEL service.",
    ["backend", "outcome"],
)

_BAGEL_LATENCY_BUCKETS = (
    0.5, 1.0, 2.0, 4.0, 6.0, 7.0, 7.5, 7.75,
    8.0, 8.25, 8.5, 9.0, 10.0, 12.0, 15.0,
    30.0, 60.0, 120.0,
)

multimodal_request_latency_seconds = Histogram(
    "multimodal_request_latency_seconds",
    "FastAPI gateway-to-BAGEL request latency.",
    ["backend"],
    buckets=_BAGEL_LATENCY_BUCKETS,
)

multimodal_gpu_memory_used_mib = Gauge(
    "multimodal_gpu_memory_used_mib",
    "Sampled GPU memory used after a successful BAGEL request.",
    ["gpu_index"],
)

multimodal_gpu_utilization_percent = Gauge(
    "multimodal_gpu_utilization_percent",
    "Sampled GPU utilization after a successful BAGEL request.",
    ["gpu_index"],
)


def update_gpu_metrics() -> None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return

    for line in result.stdout.strip().splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 3:
            continue

        gpu_index, memory_used, gpu_utilization = parts
        multimodal_gpu_memory_used_mib.labels(
            gpu_index=gpu_index,
        ).set(float(memory_used))
        multimodal_gpu_utilization_percent.labels(
            gpu_index=gpu_index,
        ).set(float(gpu_utilization))

multimodal_request_errors_total = Counter(
    "multimodal_request_errors_total",
    "Number of multimodal request failures.",
    ["backend", "error_type"],
)

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_SUFFIX_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class MultimodalGenerateResponse(BaseModel):
    response: str
    latency_seconds: float
    backend: str
    model_name: str
    image_filename: str
    image_bytes: int
    max_new_tokens: int
    temperature: float
    show_thinking: bool
    do_sample: bool


class BagelClientError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _bagel_client() -> Client:
    return Client(BAGEL_BASE_URL)


def _call_bagel(
    image_bytes: bytes,
    content_type: str,
    prompt: str,
    show_thinking: bool,
    do_sample: bool,
    temperature: float,
    max_new_tokens: int,
) -> tuple[str, float]:
    suffix = _SUFFIX_BY_CONTENT_TYPE[content_type]

    with tempfile.NamedTemporaryFile(
        suffix=suffix,
        delete=False,
    ) as temporary_file:
        temporary_file.write(image_bytes)
        temporary_path = temporary_file.name

    started = perf_counter()

    try:
        result = _bagel_client().predict(
            handle_file(temporary_path),
            prompt,
            show_thinking,
            do_sample,
            temperature,
            max_new_tokens,
            api_name="/process_understanding",
        )
    except Exception as exc:
        raise BagelClientError(str(exc)) from exc
    finally:
        Path(temporary_path).unlink(missing_ok=True)

    return str(result), perf_counter() - started


@router.get("/health")
async def multimodal_health():
    try:
        response = await asyncio.to_thread(
            urlopen,
            BAGEL_BASE_URL,
            timeout=3,
        )
        healthy = response.status == 200
    except (URLError, OSError):
        healthy = False

    if not healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "not_ready",
                "backend": "bagel_gradio",
                "base_url": BAGEL_BASE_URL,
            },
        )

    return {
        "status": "ready",
        "backend": "bagel_gradio",
        "model_name": BAGEL_MODEL_NAME,
        "base_url": BAGEL_BASE_URL,
    }


@router.post(
    "/generate",
    response_model=MultimodalGenerateResponse,
)
async def multimodal_generate(
    image: UploadFile = File(...),
    prompt: str = Form(...),
    show_thinking: bool = Form(False),
    do_sample: bool = Form(False),
    temperature: float = Form(0.3),
    max_new_tokens: int = Form(512),
):
    backend = "bagel_gradio"

    if image.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="image must be JPEG, PNG, or WEBP",
        )

    if not prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt must not be empty",
        )

    if not 0.0 <= temperature <= 2.0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="temperature must be in [0.0, 2.0]",
        )

    if not 1 <= max_new_tokens <= 1024:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_new_tokens must be in [1, 1024]",
        )

    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="image must not be empty",
        )

    if len(image_bytes) > BAGEL_MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"image exceeds {BAGEL_MAX_IMAGE_BYTES} bytes",
        )

    started = perf_counter()

    try:
        result, bagel_latency = await asyncio.wait_for(
            asyncio.to_thread(
                _call_bagel,
                image_bytes,
                image.content_type,
                prompt,
                show_thinking,
                do_sample,
                temperature,
                max_new_tokens,
            ),
            timeout=BAGEL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        latency = perf_counter() - started
        multimodal_requests_total.labels(
            backend=backend,
            outcome="timeout",
        ).inc()
        multimodal_request_errors_total.labels(
            backend=backend,
            error_type="timeout",
        ).inc()
        multimodal_request_latency_seconds.labels(
            backend=backend,
        ).observe(latency)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="BAGEL request timed out",
        )
    except BagelClientError as exc:
        latency = perf_counter() - started
        multimodal_requests_total.labels(
            backend=backend,
            outcome="upstream_error",
        ).inc()
        multimodal_request_errors_total.labels(
            backend=backend,
            error_type="upstream_error",
        ).inc()
        multimodal_request_latency_seconds.labels(
            backend=backend,
        ).observe(latency)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BAGEL upstream error: {exc}",
        )

    latency = perf_counter() - started
    multimodal_requests_total.labels(
        backend=backend,
        outcome="success",
    ).inc()
    multimodal_request_latency_seconds.labels(
        backend=backend,
    ).observe(latency)
    update_gpu_metrics()

    return MultimodalGenerateResponse(
        response=result,
        latency_seconds=latency,
        backend=backend,
        model_name=BAGEL_MODEL_NAME,
        image_filename=image.filename or "upload",
        image_bytes=len(image_bytes),
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        show_thinking=show_thinking,
        do_sample=do_sample,
    )
