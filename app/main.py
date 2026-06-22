import os

from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_fastapi_instrumentator import Instrumentator

from app.backends.errors import (
    BackendTimeoutError,
    BackendUnavailableError,
    UpstreamProtocolError,
)
from app.config import INFERENCE_BACKEND
from app.inference import backend, generate_text
from app.metrics.prometheus_metrics import (
    record_backend_failure,
    record_backend_readiness,
)
from app.resilience import CircuitOpenError
from app.schemas import GenerateRequest, GenerateResponse


app = FastAPI(title="AI Inference Service", version="0.2.0")

Instrumentator().instrument(app).expose(app)


@app.middleware("http")
async def add_gateway_instance_header(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Gateway-Instance"] = os.getenv("POD_NAME", "local")
    return response



def _backend_readiness() -> dict:
    checker = getattr(backend, "check_ready", None)

    if checker is None:
        result = {
            "ready": True,
            "backend": INFERENCE_BACKEND,
            "detail": "backend does not expose an active readiness check",
        }
    else:
        result = checker()

    record_backend_readiness(result)
    return result


@app.get("/livez")
def livez():
    return {
        "status": "live",
        "backend": INFERENCE_BACKEND,
    }


@app.get("/readyz")
def readyz():
    result = _backend_readiness()

    if not result["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result,
        )

    return {
        "status": "ready",
        **result,
    }


@app.get("/health")
def health_check():
    result = _backend_readiness()

    if not result["ready"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "degraded",
                **result,
            },
        )

    return {
        "status": "ok",
        **result,
    }


def _raise_backend_error(
    status_code: int,
    error_type: str,
    message: str,
) -> None:
    record_backend_failure(INFERENCE_BACKEND, error_type)

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error_type,
            "backend": INFERENCE_BACKEND,
            "message": message,
        },
    )


@app.post("/generate", response_model=GenerateResponse)
def generate(request: GenerateRequest, response: Response):
    if not request.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="prompt must not be empty",
        )

    try:
        result = generate_text(
            prompt=request.prompt,
            max_new_tokens=request.max_new_tokens,
            temperature=request.temperature,
            thinking_budget=request.thinking_budget,
        )
        response.headers["X-Request-ID"] = result["request_id"]
        response.headers["X-Inference-Route"] = result["route"]
        return result
    except CircuitOpenError as exc:
        _raise_backend_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "circuit_open",
            str(exc),
        )
    except BackendUnavailableError as exc:
        _raise_backend_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "backend_unavailable",
            str(exc),
        )
    except BackendTimeoutError as exc:
        _raise_backend_error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "backend_timeout",
            str(exc),
        )
    except UpstreamProtocolError as exc:
        _raise_backend_error(
            status.HTTP_502_BAD_GATEWAY,
            "upstream_protocol_error",
            str(exc),
        )
