import os


INFERENCE_BACKEND = os.getenv("INFERENCE_BACKEND", "mock")

MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "Qwen/Qwen2.5-0.5B-Instruct",
)

VLLM_BASE_URL = os.getenv(
    "VLLM_BASE_URL",
    "http://127.0.0.1:8001/v1",
)

VLLM_MODEL_NAME = os.getenv(
    "VLLM_MODEL_NAME",
    MODEL_NAME,
)

VLLM_TIMEOUT_SECONDS = float(
    os.getenv("VLLM_TIMEOUT_SECONDS", "300")
)
