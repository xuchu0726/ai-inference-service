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

VLLM_API_KEY = os.getenv(
    "VLLM_API_KEY",
    "",
)

VLLM_FALLBACK_API_KEY = os.getenv(
    "VLLM_FALLBACK_API_KEY",
    "",
)

VLLM_TIMEOUT_SECONDS = float(
    os.getenv("VLLM_TIMEOUT_SECONDS", "300")
)

VLLM_FALLBACK_TIMEOUT_SECONDS = float(
    os.getenv(
        "VLLM_FALLBACK_TIMEOUT_SECONDS",
        str(VLLM_TIMEOUT_SECONDS),
    )
)

VLLM_ENABLE_SEED_THINKING_BUDGET = (
    os.getenv("VLLM_ENABLE_SEED_THINKING_BUDGET", "false").lower() == "true"
)

MOCK_CPU_BURN_MS = int(
    os.getenv("MOCK_CPU_BURN_MS", "0")
)


TRANSFORMERS_LOAD_IN_8BIT = (
    os.getenv("TRANSFORMERS_LOAD_IN_8BIT", "false").lower() == "true"
)

TRANSFORMERS_DEVICE_MAP = os.getenv(
    "TRANSFORMERS_DEVICE_MAP",
    "auto",
)

TRANSFORMERS_DEFAULT_THINKING_BUDGET = int(
    os.getenv("TRANSFORMERS_DEFAULT_THINKING_BUDGET", "0")
)

RESILIENCE_RETRY_ATTEMPTS = int(
    os.getenv("RESILIENCE_RETRY_ATTEMPTS", "1")
)

RESILIENCE_RETRY_BACKOFF_SECONDS = float(
    os.getenv("RESILIENCE_RETRY_BACKOFF_SECONDS", "0.2")
)

RESILIENCE_FAILURE_THRESHOLD = int(
    os.getenv("RESILIENCE_FAILURE_THRESHOLD", "3")
)

RESILIENCE_RECOVERY_TIMEOUT_SECONDS = float(
    os.getenv("RESILIENCE_RECOVERY_TIMEOUT_SECONDS", "20")
)

VLLM_FALLBACK_BASE_URL = os.getenv(
    "VLLM_FALLBACK_BASE_URL",
    "",
).rstrip("/")

VLLM_FALLBACK_MODEL_NAME = os.getenv(
    "VLLM_FALLBACK_MODEL_NAME",
    VLLM_MODEL_NAME,
)

RESILIENCE_FALLBACK_THINKING_BUDGET = int(
    os.getenv("RESILIENCE_FALLBACK_THINKING_BUDGET", "512")
)

RESILIENCE_STATE_STORE = os.getenv(
    "RESILIENCE_STATE_STORE",
    "local",
).strip().lower()

if RESILIENCE_STATE_STORE not in {"local", "redis"}:
    raise ValueError(
        "RESILIENCE_STATE_STORE must be either 'local' or 'redis'"
    )

RESILIENCE_REDIS_URL = os.getenv(
    "RESILIENCE_REDIS_URL",
    "redis://127.0.0.1:6379/0",
)

RESILIENCE_REDIS_KEY_PREFIX = os.getenv(
    "RESILIENCE_REDIS_KEY_PREFIX",
    "ai-inference:resilience",
).strip().rstrip(":")

if not RESILIENCE_REDIS_KEY_PREFIX:
    raise ValueError("RESILIENCE_REDIS_KEY_PREFIX must not be empty")

RESILIENCE_REDIS_SOCKET_TIMEOUT_SECONDS = float(
    os.getenv("RESILIENCE_REDIS_SOCKET_TIMEOUT_SECONDS", "0.2")
)

RESILIENCE_REDIS_PROBE_LEASE_MS = int(
    os.getenv(
        "RESILIENCE_REDIS_PROBE_LEASE_MS",
        str(max(30_000, int(VLLM_TIMEOUT_SECONDS * 1000) + 10_000)),
    )
)

if RESILIENCE_REDIS_PROBE_LEASE_MS <= 0:
    raise ValueError("RESILIENCE_REDIS_PROBE_LEASE_MS must be positive")
