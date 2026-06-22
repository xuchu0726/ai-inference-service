from concurrent.futures import ThreadPoolExecutor
import json
import time
import urllib.request

DURATION_SECONDS = 120
WORKERS = 16
TARGET = "http://inference-gateway:8000/generate"

PAYLOAD = json.dumps(
    {
        "prompt": "hpa cpu load",
        "max_new_tokens": 8,
        "temperature": 0.0,
    }
).encode()


def worker(deadline: float) -> tuple[int, int]:
    ok = 0
    failed = 0

    while time.monotonic() < deadline:
        request = urllib.request.Request(
            TARGET,
            data=PAYLOAD,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response.read()
            ok += 1
        except Exception:
            failed += 1

    return ok, failed


def main() -> None:
    deadline = time.monotonic() + DURATION_SECONDS

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(lambda _: worker(deadline), range(WORKERS)))

    print(f"concurrency={WORKERS}")
    print(f"duration_seconds={DURATION_SECONDS}")
    print(f"successful_requests={sum(ok for ok, _ in results)}")
    print(f"failed_requests={sum(failed for _, failed in results)}")


if __name__ == "__main__":
    main()
