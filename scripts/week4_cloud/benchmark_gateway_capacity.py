#!/usr/bin/env python3
"""Week4 Gateway 容量实验：同步 generate 或异步 jobs 的受控并发压测。"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import statistics
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class RequestResult:
    index: int
    mode: str
    success: bool
    final_status: str
    http_status: int | None
    submit_latency_seconds: float | None
    end_to_end_latency_seconds: float | None
    route: str | None
    primary_attempts: int | None
    job_id: str | None
    error: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--mode", choices=("generate", "jobs"), required=True)
    parser.add_argument("--requests", type=int, required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--poll-interval-seconds", type=float, default=0.2)
    parser.add_argument("--job-timeout-seconds", type=float, default=360.0)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 420.0,
) -> tuple[int, dict[str, Any]]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"raw_error": raw}
        return exc.code, body


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile_value * len(ordered)) - 1)
    return ordered[index]


def run_one(index: int, args: argparse.Namespace) -> RequestResult:
    base_url = args.base_url.rstrip("/")
    payload = {
        "prompt": (
            "Week4 capacity validation request "
            f"index={index} nonce={uuid.uuid4().hex}"
        ),
        "max_new_tokens": args.max_new_tokens,
        "temperature": args.temperature,
        "thinking_budget": args.thinking_budget,
    }

    started = time.perf_counter()

    try:
        if args.mode == "generate":
            http_status, body = request_json(
                "POST",
                f"{base_url}/generate",
                payload,
            )
            elapsed = time.perf_counter() - started
            return RequestResult(
                index=index,
                mode=args.mode,
                success=http_status == 200,
                final_status="succeeded" if http_status == 200 else "failed",
                http_status=http_status,
                submit_latency_seconds=elapsed,
                end_to_end_latency_seconds=elapsed,
                route=body.get("route"),
                primary_attempts=body.get("primary_attempts"),
                job_id=None,
                error=None if http_status == 200 else json.dumps(body),
            )

        submit_started = time.perf_counter()
        http_status, body = request_json(
            "POST",
            f"{base_url}/jobs",
            payload,
        )
        submit_latency = time.perf_counter() - submit_started

        if http_status != 202:
            return RequestResult(
                index=index,
                mode=args.mode,
                success=False,
                final_status="submission_failed",
                http_status=http_status,
                submit_latency_seconds=submit_latency,
                end_to_end_latency_seconds=time.perf_counter() - started,
                route=None,
                primary_attempts=None,
                job_id=None,
                error=json.dumps(body),
            )

        job_id = body["job_id"]
        deadline = time.monotonic() + args.job_timeout_seconds

        while time.monotonic() < deadline:
            status_code, state = request_json(
                "GET",
                f"{base_url}/jobs/{job_id}",
                timeout_seconds=30.0,
            )

            status = state.get("status", "unknown")
            if status in {"succeeded", "failed"}:
                result = state.get("result") or {}
                return RequestResult(
                    index=index,
                    mode=args.mode,
                    success=status == "succeeded" and status_code == 200,
                    final_status=status,
                    http_status=status_code,
                    submit_latency_seconds=submit_latency,
                    end_to_end_latency_seconds=time.perf_counter() - started,
                    route=result.get("route"),
                    primary_attempts=result.get("primary_attempts"),
                    job_id=job_id,
                    error=state.get("error_message"),
                )

            time.sleep(args.poll_interval_seconds)

        return RequestResult(
            index=index,
            mode=args.mode,
            success=False,
            final_status="poll_timeout",
            http_status=None,
            submit_latency_seconds=submit_latency,
            end_to_end_latency_seconds=time.perf_counter() - started,
            route=None,
            primary_attempts=None,
            job_id=job_id,
            error=f"job did not finish within {args.job_timeout_seconds}s",
        )

    except Exception as exc:
        return RequestResult(
            index=index,
            mode=args.mode,
            success=False,
            final_status="client_error",
            http_status=None,
            submit_latency_seconds=None,
            end_to_end_latency_seconds=time.perf_counter() - started,
            route=None,
            primary_attempts=None,
            job_id=None,
            error=repr(exc),
        )


def main() -> None:
    args = parse_args()

    if args.requests <= 0 or args.concurrency <= 0:
        raise ValueError("--requests and --concurrency must be positive")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    wall_started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as executor:
        futures = [
            executor.submit(run_one, index, args)
            for index in range(args.requests)
        ]
        results = [future.result() for future in futures]
    wall_seconds = time.perf_counter() - wall_started

    rows = [asdict(result) for result in results]
    with (output_dir / "requests.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    end_to_end = [
        value.end_to_end_latency_seconds
        for value in results
        if value.end_to_end_latency_seconds is not None
    ]
    submit_latencies = [
        value.submit_latency_seconds
        for value in results
        if value.submit_latency_seconds is not None
    ]
    routes: dict[str, int] = {}
    for result in results:
        if result.route:
            routes[result.route] = routes.get(result.route, 0) + 1

    summary = {
        "mode": args.mode,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "success_count": sum(result.success for result in results),
        "failure_count": sum(not result.success for result in results),
        "error_rate": round(
            sum(not result.success for result in results) / args.requests,
            6,
        ),
        "wall_seconds": round(wall_seconds, 6),
        "completed_requests_per_second": round(
            args.requests / wall_seconds,
            6,
        ),
        "end_to_end_p50_seconds": percentile(end_to_end, 0.50),
        "end_to_end_p95_seconds": percentile(end_to_end, 0.95),
        "end_to_end_mean_seconds": (
            round(statistics.mean(end_to_end), 6) if end_to_end else None
        ),
        "submission_p50_seconds": percentile(submit_latencies, 0.50),
        "submission_p95_seconds": percentile(submit_latencies, 0.95),
        "routes": routes,
    }

    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
