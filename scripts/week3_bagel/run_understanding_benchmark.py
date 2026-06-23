#!/usr/bin/env python3
import argparse
import csv
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def percentile(values, p):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def gpu_sample():
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
    )

    rows = []
    for line in result.stdout.strip().splitlines():
        index, memory_used, gpu_util = [item.strip() for item in line.split(",")]
        rows.append(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "gpu_index": int(index),
                "memory_used_mib": int(memory_used),
                "gpu_utilization_percent": int(gpu_util),
            }
        )
    return rows


def sample_gpu(stop_event, samples, interval_seconds):
    while not stop_event.is_set():
        try:
            samples.extend(gpu_sample())
        except Exception as exc:
            samples.append(
                {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                }
            )
        stop_event.wait(interval_seconds)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8000/multimodal/generate",
    )
    parser.add_argument(
        "--manifest",
        default="data/week3_bagel/manifest.json",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    manifest_path = root / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    image_path = root / manifest["local_path"]

    results_dir = root / "results/week3_bagel"
    evidence_dir = root / "evidence/week3_bagel"
    results_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    run_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    case_slug = "".join(
        char if char.isalnum() or char in ("-", "_") else "_"
        for char in manifest["case_id"]
    )
    records = []
    gpu_samples = []

    stop_event = threading.Event()
    sampler = threading.Thread(
        target=sample_gpu,
        args=(stop_event, gpu_samples, args.sample_interval),
        daemon=True,
    )
    sampler.start()

    try:
        for run_id in range(1, args.runs + 1):
            started = time.perf_counter()

            try:
                with image_path.open("rb") as image_file:
                    response = httpx.post(
                        args.endpoint,
                        files={
                            "image": (
                                image_path.name,
                                image_file,
                                "image/jpeg",
                            )
                        },
                        data={
                            "prompt": manifest["prompt"],
                            "show_thinking": str(
                                manifest["show_thinking"]
                            ).lower(),
                            "do_sample": str(
                                manifest["do_sample"]
                            ).lower(),
                            "temperature": str(manifest["temperature"]),
                            "max_new_tokens": str(
                                manifest["max_new_tokens"]
                            ),
                        },
                        timeout=180,
                    )

                elapsed = time.perf_counter() - started
                payload = response.json()

                records.append(
                    {
                        "run_id": run_id,
                        "http_status": response.status_code,
                        "success": response.is_success,
                        "client_latency_seconds": elapsed,
                        "service_latency_seconds": payload.get(
                            "latency_seconds"
                        ),
                        "response_chars": len(payload.get("response", "")),
                        "response": payload.get("response", ""),
                        "error": "",
                    }
                )
            except Exception as exc:
                elapsed = time.perf_counter() - started
                records.append(
                    {
                        "run_id": run_id,
                        "http_status": None,
                        "success": False,
                        "client_latency_seconds": elapsed,
                        "service_latency_seconds": None,
                        "response_chars": 0,
                        "response": "",
                        "error": repr(exc),
                    }
                )
    finally:
        stop_event.set()
        sampler.join(timeout=5)

    success_latencies = [
        record["client_latency_seconds"]
        for record in records
        if record["success"]
    ]

    summary = {
        "case_id": manifest["case_id"],
        "endpoint": args.endpoint,
        "runs_requested": args.runs,
        "runs_succeeded": len(success_latencies),
        "success_rate": len(success_latencies) / args.runs,
        "client_latency_seconds": {
            "min": min(success_latencies) if success_latencies else None,
            "p50": percentile(success_latencies, 0.50),
            "p95": percentile(success_latencies, 0.95),
            "max": max(success_latencies) if success_latencies else None,
        },
        "gpu_samples": gpu_samples,
        "records": records,
        "manifest": manifest,
    }

    json_path = results_dir / f"bagel_understanding_{case_slug}_n{args.runs}_{run_tag}.json"
    csv_path = results_dir / f"bagel_understanding_{case_slug}_n{args.runs}_{run_tag}.csv"
    evidence_path = evidence_dir / f"bagel_understanding_{case_slug}_n{args.runs}_{run_tag}.txt"

    json_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "run_id",
                "http_status",
                "success",
                "client_latency_seconds",
                "service_latency_seconds",
                "response_chars",
                "response",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(records)

    peak_memory = max(
        (
            sample.get("memory_used_mib", 0)
            for sample in gpu_samples
            if "memory_used_mib" in sample
        ),
        default=0,
    )
    peak_util = max(
        (
            sample.get("gpu_utilization_percent", 0)
            for sample in gpu_samples
            if "gpu_utilization_percent" in sample
        ),
        default=0,
    )

    evidence_path.write_text(
        "\n".join(
            [
                "===== BAGEL 图文理解审计摘要 =====",
                f"case_id={manifest['case_id']}",
                f"endpoint={args.endpoint}",
                f"manifest={manifest_path.relative_to(root)}",
                f"runs_requested={args.runs}",
                f"runs_succeeded={summary['runs_succeeded']}",
                f"success_rate={summary['success_rate']:.3f}",
                f"client_p50_seconds={summary['client_latency_seconds']['p50']}",
                f"client_p95_seconds={summary['client_latency_seconds']['p95']}",
                f"peak_gpu_memory_mib={peak_memory}",
                f"peak_gpu_utilization_percent={peak_util}",
                f"json={json_path.relative_to(root)}",
                f"csv={csv_path.relative_to(root)}",
                "边界：该延迟从本机 FastAPI 请求开始计时，包含",
                "FastAPI、Gradio Client 与 BAGEL 推理；不包含浏览器",
                "交互及 RunPod 公网代理开销。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(
        {
            "json": str(json_path),
            "csv": str(csv_path),
            "evidence": str(evidence_path),
            "runs_succeeded": summary["runs_succeeded"],
            "p50_seconds": summary["client_latency_seconds"]["p50"],
            "p95_seconds": summary["client_latency_seconds"]["p95"],
            "peak_gpu_memory_mib": peak_memory,
            "peak_gpu_utilization_percent": peak_util,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
