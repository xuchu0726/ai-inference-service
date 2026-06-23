import os

BAGEL_BASE_URL = os.getenv(
    "BAGEL_BASE_URL",
    "http://127.0.0.1:7860",
).rstrip("/")

BAGEL_TIMEOUT_SECONDS = float(
    os.getenv("BAGEL_TIMEOUT_SECONDS", "120")
)

BAGEL_MAX_IMAGE_BYTES = int(
    os.getenv("BAGEL_MAX_IMAGE_BYTES", str(10 * 1024 * 1024))
)

BAGEL_MODEL_NAME = os.getenv(
    "BAGEL_MODEL_NAME",
    "ByteDance-Seed/BAGEL-7B-MoT",
)
