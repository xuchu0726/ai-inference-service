#!/usr/bin/env python3
"""A100 上的 RMSNorm + INT8 Triton 微内核正确性与性能实验。"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import torch

from app.kernels.rmsnorm_int8 import (
    dequantize_per_row_int8,
    rmsnorm_int8_fused,
    rmsnorm_int8_reference,
    triton_is_available,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--repetitions", type=int, default=100)
    return parser.parse_args()


def measure_ms(fn, warmup: int, repetitions: int) -> list[float]:
    for _ in range(warmup):
        fn()

    torch.cuda.synchronize()

    samples: list[float] = []
    for _ in range(repetitions):
        started = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        samples.append((time.perf_counter() - started) * 1000)

    return samples


def percentile(values: list[float], point: float) -> float:
    ordered = sorted(values)
    index = max(0, int(round((len(ordered) - 1) * point)))
    return ordered[index]


def main() -> None:
    args = parse_args()

    if not triton_is_available():
        raise RuntimeError("CUDA + Triton are required")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = [
        {"rows": 1, "hidden_size": 1024, "dtype": torch.float16},
        {"rows": 8, "hidden_size": 4096, "dtype": torch.float16},
        {"rows": 32, "hidden_size": 4096, "dtype": torch.bfloat16},
        {"rows": 32, "hidden_size": 8192, "dtype": torch.bfloat16},
    ]

    rows: list[dict[str, object]] = []

    for case in cases:
        torch.manual_seed(20260701)

        x = torch.randn(
            case["rows"],
            case["hidden_size"],
            device="cuda",
            dtype=case["dtype"],
        )
        weight = torch.randn(
            case["hidden_size"],
            device="cuda",
            dtype=case["dtype"],
        )

        expected_q, expected_scales = rmsnorm_int8_reference(x, weight)
        actual_q, actual_scales = rmsnorm_int8_fused(x, weight)

        dequant_error = (
            dequantize_per_row_int8(actual_q, actual_scales)
            - dequantize_per_row_int8(expected_q, expected_scales)
        ).abs().max().item()

        reference_ms = measure_ms(
            lambda: rmsnorm_int8_reference(x, weight),
            args.warmup,
            args.repetitions,
        )
        fused_ms = measure_ms(
            lambda: rmsnorm_int8_fused(x, weight),
            args.warmup,
            args.repetitions,
        )

        rows.append(
            {
                "rows": case["rows"],
                "hidden_size": case["hidden_size"],
                "dtype": str(case["dtype"]),
                "quantized_exact_match": bool(torch.equal(actual_q, expected_q)),
                "scale_max_abs_error": float(
                    (actual_scales - expected_scales).abs().max().item()
                ),
                "dequantized_max_abs_error": float(dequant_error),
                "reference_p50_ms": percentile(reference_ms, 0.50),
                "reference_p95_ms": percentile(reference_ms, 0.95),
                "fused_p50_ms": percentile(fused_ms, 0.50),
                "fused_p95_ms": percentile(fused_ms, 0.95),
                "p50_speedup": percentile(reference_ms, 0.50)
                / percentile(fused_ms, 0.50),
            }
        )

    with (output_dir / "triton_rmsnorm_int8_results.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "device": torch.cuda.get_device_name(0),
        "warmup": args.warmup,
        "repetitions": args.repetitions,
        "all_quantized_exact_match": all(
            bool(row["quantized_exact_match"]) for row in rows
        ),
        "rows": rows,
    }

    (output_dir / "triton_rmsnorm_int8_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
