import os


INFERENCE_BACKEND = os.getenv("INFERENCE_BACKEND", "mock")

MODEL_NAME = os.getenv(
    "MODEL_NAME",
    "Qwen/Qwen2.5-0.5B-Instruct",
)
