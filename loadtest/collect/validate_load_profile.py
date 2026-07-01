#!/usr/bin/env python3
"""校验 JMeter JTL 在稳定窗口内是否满足目标负载画像。"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jtl", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--target-qps", type=float, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=0.0)
    parser.add_argument("--max-relative-qps-deviation", type=float, default=0.10)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--min-samples", type=int, default=1)
    parser.add_argument("--fail-on-invalid", action="store_true")
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.jtl).open(encoding="utf-8")))

    samples: list[dict[str, object]] = []
    for row in rows:
        try:
            timestamp_ms = int(row["timeStamp"])
            elapsed_ms = float(row["elapsed"])
        except (KeyError, TypeError, ValueError):
            continue

        samples.append(
            {
                "timestamp_ms": timestamp_ms,
                "end_ms": timestamp_ms + elapsed_ms,
                "elapsed_ms": elapsed_ms,
                "success": row.get("success") == "true",
                "response_code": row.get("responseCode", ""),
            }
        )

    invalid_reasons: list[str] = []

    if not samples:
        invalid_reasons.append("no_parseable_jtl_samples")
        window_samples: list[dict[str, object]] = []
        window_start_ms = None
        window_end_ms = None
    else:
        first_timestamp_ms = min(int(sample["timestamp_ms"]) for sample in samples)
        window_start_ms = first_timestamp_ms + args.warmup_seconds * 1000.0
        window_samples = [
            sample
            for sample in samples
            if float(sample["timestamp_ms"]) >= window_start_ms
        ]
        window_end_ms = (
            max(float(sample["end_ms"]) for sample in window_samples)
            if window_samples
            else None
        )

    if len(window_samples) < args.min_samples:
        invalid_reasons.append(
            f"stable_window_sample_count_below_minimum:"
            f"{len(window_samples)}<{args.min_samples}"
        )

    window_seconds = (
        (window_end_ms - window_start_ms) / 1000.0
        if window_start_ms is not None
        and window_end_ms is not None
        and window_end_ms > window_start_ms
        else None
    )

    actual_qps = (
        len(window_samples) / window_seconds
        if window_seconds and window_seconds > 0
        else None
    )

    if args.target_qps <= 0:
        qps_relative_deviation = None
    elif actual_qps is None:
        qps_relative_deviation = None
        invalid_reasons.append("actual_qps_unavailable")
    else:
        qps_relative_deviation = abs(actual_qps - args.target_qps) / args.target_qps
        if qps_relative_deviation > args.max_relative_qps_deviation:
            invalid_reasons.append(
                "actual_qps_outside_allowed_deviation:"
                f"{qps_relative_deviation:.6f}>"
                f"{args.max_relative_qps_deviation:.6f}"
            )

    success_count = sum(bool(sample["success"]) for sample in window_samples)
    failure_count = len(window_samples) - success_count
    error_rate = (
        failure_count / len(window_samples)
        if window_samples
        else None
    )

    if error_rate is not None and error_rate > args.max_error_rate:
        invalid_reasons.append(
            f"error_rate_above_threshold:"
            f"{error_rate:.6f}>{args.max_error_rate:.6f}"
        )

    elapsed_values = [
        float(sample["elapsed_ms"])
        for sample in window_samples
    ]

    payload = {
        "target_qps": args.target_qps,
        "warmup_seconds": args.warmup_seconds,
        "max_relative_qps_deviation": args.max_relative_qps_deviation,
        "max_error_rate": args.max_error_rate,
        "stable_window_sample_count": len(window_samples),
        "stable_window_seconds": round(window_seconds, 6)
        if window_seconds is not None
        else None,
        "actual_qps": round(actual_qps, 6)
        if actual_qps is not None
        else None,
        "qps_relative_deviation": round(qps_relative_deviation, 6)
        if qps_relative_deviation is not None
        else None,
        "success_count": success_count,
        "failure_count": failure_count,
        "error_rate": round(error_rate, 6)
        if error_rate is not None
        else None,
        "response_codes": sorted(
            {str(sample["response_code"]) for sample in window_samples}
        ),
        "latency_p50_ms": percentile(elapsed_values, 0.50),
        "latency_p95_ms": percentile(elapsed_values, 0.95),
        "latency_max_ms": max(elapsed_values) if elapsed_values else None,
        "profile_valid": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.fail_on_invalid and invalid_reasons:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
