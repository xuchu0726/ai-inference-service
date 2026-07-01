#!/usr/bin/env python3
"""执行 BAGEL 图文 workload，并归档请求级、指标级和 GPU 采样证据。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import statistics
import struct
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


REPO_ROOT = Path(__file__).resolve().parents[2]


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def image_dimensions(path: Path) -> tuple[int | None, int | None]:
    """无 Pillow 依赖地读取 PNG/JPEG/WebP 的像素宽高。"""
    data = path.read_bytes()[:65536]

    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height

    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            offset += 2
            while marker == 0xFF and offset < len(data):
                marker = data[offset]
                offset += 1
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(data):
                break
            segment_length = int.from_bytes(data[offset:offset + 2], "big")
            if segment_length < 2 or offset + segment_length > len(data):
                break
            if marker in {
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            }:
                height = int.from_bytes(data[offset + 3:offset + 5], "big")
                width = int.from_bytes(data[offset + 5:offset + 7], "big")
                return width, height
            offset += segment_length

    return None, None


def gpu_sample() -> list[dict[str, Any]]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    records: list[dict[str, Any]] = []

    for line in result.stdout.strip().splitlines():
        index, memory_used, utilization = [item.strip() for item in line.split(",")]
        records.append(
            {
                "timestamp_utc": timestamp,
                "gpu_index": int(index),
                "memory_used_mib": int(memory_used),
                "gpu_utilization_percent": int(utilization),
            }
        )
    return records


def sample_gpu(
    stop_event: threading.Event,
    samples: list[dict[str, Any]],
    interval_seconds: float,
) -> None:
    while not stop_event.is_set():
        try:
            samples.extend(gpu_sample())
        except Exception as exc:  # 允许本地静态环境无 nvidia-smi。
            samples.append(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        stop_event.wait(interval_seconds)


def derive_metrics_endpoint(endpoint: str) -> str:
    parsed = urlsplit(endpoint)
    return f"{parsed.scheme}://{parsed.netloc}/metrics"


def save_metrics_snapshot(
    client: httpx.Client,
    endpoint: str,
    destination: Path,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = client.get(endpoint, timeout=15)
        response.raise_for_status()
        destination.write_text(response.text, encoding="utf-8")
        return {
            "endpoint": endpoint,
            "success": True,
            "http_status": response.status_code,
            "latency_seconds": time.perf_counter() - started,
            "path": str(destination),
        }
    except Exception as exc:
        destination.write_text(
            f"metrics_snapshot_error={type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        return {
            "endpoint": endpoint,
            "success": False,
            "http_status": None,
            "latency_seconds": time.perf_counter() - started,
            "error": f"{type(exc).__name__}: {exc}",
            "path": str(destination),
        }


def load_manifest(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    required = {
        "case_id",
        "source_case_id",
        "scenario",
        "repeat_index",
        "image_path",
        "image_sha256",
        "prompt",
        "show_thinking",
        "do_sample",
        "temperature",
        "max_new_tokens",
    }

    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(
                f"manifest line {line_number} missing required fields: {missing}"
            )
        records.append(record)

    if not records:
        raise ValueError(f"manifest contains no records: {path}")

    return records


def prepare_case(case: dict[str, Any]) -> dict[str, Any]:
    image_path = REPO_ROOT / case["image_path"]
    if not image_path.is_file():
        raise FileNotFoundError(f"image missing for {case['case_id']}: {image_path}")

    image_bytes = image_path.read_bytes()
    actual_sha256 = hashlib.sha256(image_bytes).hexdigest()
    if actual_sha256 != case["image_sha256"]:
        raise ValueError(
            f"image sha256 mismatch for {case['case_id']}: "
            f"expected={case['image_sha256']} actual={actual_sha256}"
        )

    width, height = image_dimensions(image_path)
    content_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"

    return {
        **case,
        "_absolute_image_path": image_path,
        "_image_bytes": image_bytes,
        "_content_type": content_type,
        "_image_width": width,
        "_image_height": height,
    }


def run_case(
    endpoint: str,
    case: dict[str, Any],
    timeout_seconds: float,
    manifest_index: int,
) -> dict[str, Any]:
    started_utc = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()

    base_record: dict[str, Any] = {
        "manifest_index": manifest_index,
        "case_id": case["case_id"],
        "source_case_id": case["source_case_id"],
        "scenario": case["scenario"],
        "repeat_index": case["repeat_index"],
        "image_path": case["image_path"],
        "image_sha256": case["image_sha256"],
        "image_content_type": case["_content_type"],
        "image_bytes": len(case["_image_bytes"]),
        "image_width": case["_image_width"],
        "image_height": case["_image_height"],
        "prompt_variant": case.get("prompt_variant", "default"),
        "prompt_chars": len(case["prompt"]),
        "prompt_utf8_bytes": len(case["prompt"].encode("utf-8")),
        "show_thinking": case["show_thinking"],
        "do_sample": case["do_sample"],
        "temperature": case["temperature"],
        "max_new_tokens": case["max_new_tokens"],
        "started_at_utc": started_utc,
    }

    try:
        response = httpx.post(
            endpoint,
            files={
                "image": (
                    case["_absolute_image_path"].name,
                    case["_image_bytes"],
                    case["_content_type"],
                )
            },
            data={
                "prompt": case["prompt"],
                "show_thinking": str(case["show_thinking"]).lower(),
                "do_sample": str(case["do_sample"]).lower(),
                "temperature": str(case["temperature"]),
                "max_new_tokens": str(case["max_new_tokens"]),
            },
            timeout=timeout_seconds,
        )
        client_latency = time.perf_counter() - started

        try:
            payload = response.json()
        except json.JSONDecodeError:
            payload = {}

        success = response.is_success
        response_text = str(payload.get("response", "")) if success else ""
        error = "" if success else response.text[:2000]
        error_type = "" if success else f"http_{response.status_code}"

        return {
            **base_record,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "http_status": response.status_code,
            "success": success,
            "client_latency_seconds": client_latency,
            "service_latency_seconds": payload.get("latency_seconds"),
            "response_chars": len(response_text),
            "response": response_text,
            "error_type": error_type,
            "error": error,
        }
    except Exception as exc:
        return {
            **base_record,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "http_status": None,
            "success": False,
            "client_latency_seconds": time.perf_counter() - started,
            "service_latency_seconds": None,
            "response_chars": 0,
            "response": "",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    successful = [record for record in records if record["success"]]
    latencies = [
        float(record["client_latency_seconds"])
        for record in successful
        if record["client_latency_seconds"] is not None
    ]
    service_latencies = [
        float(record["service_latency_seconds"])
        for record in successful
        if record["service_latency_seconds"] is not None
    ]

    errors: dict[str, int] = {}
    for record in records:
        if not record["success"]:
            key = record["error_type"] or "unknown"
            errors[key] = errors.get(key, 0) + 1

    by_source_case: dict[str, dict[str, Any]] = {}
    for source_case_id in sorted({record["source_case_id"] for record in records}):
        group = [
            record for record in records
            if record["source_case_id"] == source_case_id
        ]
        group_successful = [record for record in group if record["success"]]
        group_latencies = [
            float(record["client_latency_seconds"])
            for record in group_successful
        ]
        by_source_case[source_case_id] = {
            "runs_requested": len(group),
            "runs_succeeded": len(group_successful),
            "success_rate": len(group_successful) / len(group),
            "client_p50_seconds": percentile(group_latencies, 0.50),
            "client_p95_seconds": percentile(group_latencies, 0.95),
        }

    return {
        "runs_requested": len(records),
        "runs_succeeded": len(successful),
        "success_rate": len(successful) / len(records),
        "client_latency_seconds": {
            "min": min(latencies) if latencies else None,
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
            "mean": statistics.fmean(latencies) if latencies else None,
        },
        "service_latency_seconds": {
            "p50": percentile(service_latencies, 0.50),
            "p95": percentile(service_latencies, 0.95),
        },
        "error_counts": errors,
        "by_source_case": by_source_case,
    }


def gpu_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [
        sample for sample in samples
        if "memory_used_mib" in sample and "gpu_utilization_percent" in sample
    ]
    return {
        "sample_count": len(samples),
        "valid_sample_count": len(valid),
        "peak_memory_mib": max(
            (int(sample["memory_used_mib"]) for sample in valid),
            default=None,
        ),
        "peak_utilization_percent": max(
            (int(sample["gpu_utilization_percent"]) for sample in valid),
            default=None,
        ),
        "mean_utilization_percent": (
            statistics.fmean(
                float(sample["gpu_utilization_percent"]) for sample in valid
            )
            if valid
            else None
        ),
        "sampling_errors": [
            sample["error"] for sample in samples if "error" in sample
        ],
    }


def write_csv(records: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "manifest_index",
        "case_id",
        "source_case_id",
        "scenario",
        "repeat_index",
        "image_path",
        "image_sha256",
        "image_content_type",
        "image_bytes",
        "image_width",
        "image_height",
        "prompt_variant",
        "prompt_chars",
        "prompt_utf8_bytes",
        "show_thinking",
        "do_sample",
        "temperature",
        "max_new_tokens",
        "started_at_utc",
        "finished_at_utc",
        "http_status",
        "success",
        "client_latency_seconds",
        "service_latency_seconds",
        "response_chars",
        "error_type",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({name: record.get(name) for name in fieldnames})


def main() -> None:
    parser = argparse.ArgumentParser(
        description="执行 BAGEL Week4 图文 workload 并归档可靠性、延迟与资源证据。"
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8000/multimodal/generate",
    )
    parser.add_argument(
        "--manifest",
        default="data/week4_workloads/bagel_reliability_n30.jsonl",
    )
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=0.5)
    parser.add_argument(
        "--metrics-endpoint",
        default=None,
        help="默认由 --endpoint 推导为 http://host:port/metrics。",
    )
    parser.add_argument(
        "--output-root",
        default="results/week4_bagel",
    )
    parser.add_argument(
        "--disable-gpu-sampling",
        action="store_true",
    )
    parser.add_argument(
        "--disable-metrics-snapshot",
        action="store_true",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be >= 1")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be > 0")
    if args.sample_interval_seconds <= 0:
        raise SystemExit("--sample-interval-seconds must be > 0")

    manifest_path = REPO_ROOT / args.manifest
    cases = [prepare_case(case) for case in load_manifest(manifest_path)]

    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_name = f"bagel_n{len(cases)}_c{args.concurrency}_{run_tag}"
    output_dir = REPO_ROOT / args.output_root / run_name
    evidence_dir = REPO_ROOT / "evidence/week4_bagel" / run_name
    output_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)

    metrics_endpoint = args.metrics_endpoint or derive_metrics_endpoint(args.endpoint)
    metrics_client = httpx.Client()

    metrics_before: dict[str, Any] | None = None
    if not args.disable_metrics_snapshot:
        metrics_before = save_metrics_snapshot(
            metrics_client,
            metrics_endpoint,
            evidence_dir / "gateway_metrics_before.prom",
        )

    gpu_samples: list[dict[str, Any]] = []
    stop_event = threading.Event()
    sampler: threading.Thread | None = None
    if not args.disable_gpu_sampling:
        sampler = threading.Thread(
            target=sample_gpu,
            args=(stop_event, gpu_samples, args.sample_interval_seconds),
            daemon=True,
        )
        sampler.start()

    try:
        records: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {
                executor.submit(
                    run_case,
                    args.endpoint,
                    case,
                    args.timeout_seconds,
                    index,
                ): index
                for index, case in enumerate(cases, 1)
            }
            for future in as_completed(futures):
                records.append(future.result())
        records.sort(key=lambda record: int(record["manifest_index"]))
    finally:
        stop_event.set()
        if sampler is not None:
            sampler.join(timeout=10)

    metrics_after: dict[str, Any] | None = None
    if not args.disable_metrics_snapshot:
        metrics_after = save_metrics_snapshot(
            metrics_client,
            metrics_endpoint,
            evidence_dir / "gateway_metrics_after.prom",
        )
    metrics_client.close()

    records_jsonl_path = output_dir / "records.jsonl"
    with records_jsonl_path.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")

    records_csv_path = output_dir / "request_metrics.csv"
    write_csv(records, records_csv_path)

    gpu_samples_path = output_dir / "gpu_samples.jsonl"
    with gpu_samples_path.open("w", encoding="utf-8") as output:
        for sample in gpu_samples:
            output.write(json.dumps(sample, ensure_ascii=False) + "\n")

    summary = {
        "run_name": run_name,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.endpoint,
        "metrics_endpoint": metrics_endpoint,
        "manifest": str(manifest_path.relative_to(REPO_ROOT)),
        "manifest_records": len(cases),
        "concurrency": args.concurrency,
        "timeout_seconds": args.timeout_seconds,
        "request_summary": summarize_records(records),
        "gpu_summary": gpu_summary(gpu_samples),
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "artifacts": {
            "records_jsonl": str(records_jsonl_path.relative_to(REPO_ROOT)),
            "request_metrics_csv": str(records_csv_path.relative_to(REPO_ROOT)),
            "gpu_samples_jsonl": str(gpu_samples_path.relative_to(REPO_ROOT)),
        },
        "boundary": (
            "延迟为同机客户端向 FastAPI gateway 发起请求至完整响应返回的 E2E 时延，"
            "包含 multipart 上传、FastAPI、Gradio Client 与 BAGEL 推理；"
            "不包含浏览器交互或公网代理开销。"
        ),
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    request_summary = summary["request_summary"]
    gpu_info = summary["gpu_summary"]
    evidence_path = evidence_dir / "validation_summary.txt"
    evidence_path.write_text(
        "\n".join(
            [
                "===== Week4 BAGEL workload validation =====",
                f"run_name={run_name}",
                f"endpoint={args.endpoint}",
                f"manifest={manifest_path.relative_to(REPO_ROOT)}",
                f"runs_requested={request_summary['runs_requested']}",
                f"runs_succeeded={request_summary['runs_succeeded']}",
                f"success_rate={request_summary['success_rate']:.6f}",
                f"concurrency={args.concurrency}",
                f"client_p50_seconds={request_summary['client_latency_seconds']['p50']}",
                f"client_p95_seconds={request_summary['client_latency_seconds']['p95']}",
                f"peak_gpu_memory_mib={gpu_info['peak_memory_mib']}",
                f"peak_gpu_utilization_percent={gpu_info['peak_utilization_percent']}",
                f"records={records_jsonl_path.relative_to(REPO_ROOT)}",
                f"summary={summary_path.relative_to(REPO_ROOT)}",
                f"gpu_samples={gpu_samples_path.relative_to(REPO_ROOT)}",
                "status=PASS" if request_summary["runs_succeeded"] == len(cases)
                else "status=PARTIAL_OR_FAILED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "run_name": run_name,
                "summary": str(summary_path.relative_to(REPO_ROOT)),
                "evidence": str(evidence_path.relative_to(REPO_ROOT)),
                "runs_succeeded": request_summary["runs_succeeded"],
                "runs_requested": request_summary["runs_requested"],
                "success_rate": request_summary["success_rate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
