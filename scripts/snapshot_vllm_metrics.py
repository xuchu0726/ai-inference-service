import argparse
import time
import urllib.request
from pathlib import Path


TARGET_PATTERNS = [
    "vllm:num_requests_running",
    "vllm:num_requests_waiting",
    "vllm:kv_cache_usage_perc",
    "vllm:prefix_cache_queries_total",
    "vllm:prefix_cache_hits_total",
]


def fetch_metrics(url: str, timeout_seconds: float) -> str:
    with urllib.request.urlopen(url, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8", errors="replace")


def filter_metrics(raw: str) -> list[str]:
    lines = []
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        if any(pattern in line for pattern in TARGET_PATTERNS):
            lines.append(line)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snapshot selected vLLM Prometheus metrics."
    )
    parser.add_argument("--url", default="http://127.0.0.1:8002/metrics")
    parser.add_argument("--output", default="results/week2_vllm_metrics_snapshot.txt")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw = fetch_metrics(args.url, args.timeout_seconds)
    selected = filter_metrics(raw)

    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"url: {args.url}\n")
        f.write("\n")
        f.write("===== selected vLLM metrics =====\n")
        if selected:
            for line in selected:
                f.write(line + "\n")
        else:
            f.write("No selected vLLM metrics found.\n")
        f.write("\n")
        f.write("===== target metric patterns =====\n")
        for pattern in TARGET_PATTERNS:
            f.write(pattern + "\n")

    print(f"saved_metrics_snapshot: {output_path}")
    print(f"matched_lines: {len(selected)}")


if __name__ == "__main__":
    main()
