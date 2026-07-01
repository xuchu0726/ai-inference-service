#!/usr/bin/env python3
"""将 JMeter CSV JTL 汇总为可归档 JSON。"""

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
    parser.add_argument("--mode", required=True)
    parser.add_argument("--target-qps", type=float, required=True)
    parser.add_argument("--configured-threads", type=int, required=True)
    args = parser.parse_args()

    jtl_path = Path(args.jtl)
    rows = list(csv.DictReader(jtl_path.open(encoding="utf-8")))

    elapsed_ms = [
        float(row["elapsed"])
        for row in rows
        if row.get("elapsed")
    ]
    timestamps_ms = [
        int(row["timeStamp"])
        for row in rows
        if row.get("timeStamp")
    ]
    success_count = sum(row.get("success") == "true" for row in rows)
    failure_count = len(rows) - success_count

    wall_seconds = None
    actual_rps = None
    if len(timestamps_ms) >= 2:
        wall_seconds = (max(timestamps_ms) - min(timestamps_ms)) / 1000.0
        if wall_seconds > 0:
            actual_rps = len(rows) / wall_seconds

    payload = {
        "mode": args.mode,
        "target_qps": args.target_qps,
        "configured_threads": args.configured_threads,
        "sample_count": len(rows),
        "success_count": success_count,
        "failure_count": failure_count,
        "error_rate": (
            round(failure_count / len(rows), 6)
            if rows
            else None
        ),
        "response_codes": sorted(
            {row.get("responseCode") for row in rows}
        ),
        "wall_seconds": round(wall_seconds, 6)
        if wall_seconds is not None
        else None,
        "actual_requests_per_second": round(actual_rps, 6)
        if actual_rps is not None
        else None,
        "latency_p50_ms": percentile(elapsed_ms, 0.50),
        "latency_p95_ms": percentile(elapsed_ms, 0.95),
        "latency_max_ms": max(elapsed_ms) if elapsed_ms else None,
        "latency_mean_ms": (
            round(sum(elapsed_ms) / len(elapsed_ms), 6)
            if elapsed_ms
            else None
        ),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
