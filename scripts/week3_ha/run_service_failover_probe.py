import argparse
import csv
import sys
import time
import urllib.error
import urllib.request


def request_once(target: str, timeout: float) -> tuple[int, str, str]:
    response = urllib.request.urlopen(target, timeout=timeout)
    instance = response.headers.get("X-Gateway-Instance", "missing")
    return response.status, instance, ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--duration-seconds", type=float, default=25.0)
    parser.add_argument("--interval-seconds", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    args = parser.parse_args()

    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "timestamp_unix",
            "latency_ms",
            "ok",
            "http_status",
            "instance",
            "error",
        ],
    )
    writer.writeheader()
    sys.stdout.flush()

    deadline = time.monotonic() + args.duration_seconds

    while time.monotonic() < deadline:
        started = time.time()
        status = ""
        instance = ""
        error = ""
        ok = 0

        try:
            status, instance, error = request_once(
                args.target,
                args.timeout_seconds,
            )
            ok = int(200 <= status < 300)
        except urllib.error.HTTPError as exc:
            status = exc.code
            error = str(exc)
        except Exception as exc:
            error = repr(exc)

        latency_ms = (time.time() - started) * 1000.0

        writer.writerow(
            {
                "timestamp_unix": f"{started:.6f}",
                "latency_ms": f"{latency_ms:.3f}",
                "ok": ok,
                "http_status": status,
                "instance": instance,
                "error": error,
            }
        )
        sys.stdout.flush()

        sleep_seconds = args.interval_seconds - (time.time() - started)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()
