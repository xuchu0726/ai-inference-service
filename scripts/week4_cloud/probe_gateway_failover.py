#!/usr/bin/env python3
"""对 Gateway /generate 路径进行故障切换与恢复探测。"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProbeResult:
    index: int
    status_code: int | None
    success: bool
    route: str | None
    primary_attempts: int | None
    latency_seconds: float
    error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=3)
    parser.add_argument("--interval-seconds", type=float, default=0.5)
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def post_json(url: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=360.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}


def main() -> None:
    args = parse_args()

    if args.requests <= 0:
        raise ValueError("--requests must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[ProbeResult] = []
    base_url = args.base_url.rstrip("/")

    for index in range(1, args.requests + 1):
        started = time.perf_counter()

        try:
            status_code, body = post_json(
                f"{base_url}/generate",
                {
                    "prompt": (
                        "Week4 failover probe. "
                        f"Return a short acknowledgement. probe_index={index}"
                    ),
                    "max_new_tokens": args.max_new_tokens,
                    "temperature": 0.0,
                    "thinking_budget": 0,
                },
            )

            results.append(
                ProbeResult(
                    index=index,
                    status_code=status_code,
                    success=status_code == 200,
                    route=body.get("route"),
                    primary_attempts=body.get("primary_attempts"),
                    latency_seconds=round(time.perf_counter() - started, 6),
                    error=None if status_code == 200 else json.dumps(body),
                )
            )
        except Exception as exc:
            results.append(
                ProbeResult(
                    index=index,
                    status_code=None,
                    success=False,
                    route=None,
                    primary_attempts=None,
                    latency_seconds=round(time.perf_counter() - started, 6),
                    error=repr(exc),
                )
            )

        if index < args.requests:
            time.sleep(args.interval_seconds)

    rows = [asdict(result) for result in results]

    with (output_dir / "probe_requests.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    routes: dict[str, int] = {}
    for result in results:
        if result.route:
            routes[result.route] = routes.get(result.route, 0) + 1

    summary = {
        "base_url": base_url,
        "request_count": len(results),
        "success_count": sum(result.success for result in results),
        "failure_count": sum(not result.success for result in results),
        "routes": routes,
        "results": rows,
    }

    (output_dir / "probe_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
