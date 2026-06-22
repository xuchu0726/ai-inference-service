import argparse
import csv
import time
import urllib.error
import urllib.request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--duration-seconds", type=float, default=35.0)
    parser.add_argument("--interval-seconds", type=float, default=0.1)
    parser.add_argument("--timeout-seconds", type=float, default=2.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.duration_seconds
    writer = csv.writer(__import__("sys").stdout)
    writer.writerow(
        [
            "timestamp_unix",
            "latency_ms",
            "ok",
            "http_status",
            "gateway_instance",
            "error",
        ]
    )

    while time.monotonic() < deadline:
        started = time.perf_counter()
        timestamp = time.time()

        try:
            with urllib.request.urlopen(args.url, timeout=args.timeout_seconds) as response:
                response.read()
                latency_ms = (time.perf_counter() - started) * 1000
                writer.writerow(
                    [
                        f"{timestamp:.6f}",
                        f"{latency_ms:.3f}",
                        "1",
                        response.status,
                        response.headers.get("X-Gateway-Instance", ""),
                        "",
                    ]
                )
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            writer.writerow(
                [
                    f"{timestamp:.6f}",
                    f"{latency_ms:.3f}",
                    "0",
                    "",
                    "",
                    str(exc),
                ]
            )

        __import__("sys").stdout.flush()
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
