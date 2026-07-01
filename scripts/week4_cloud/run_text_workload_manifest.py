#!/usr/bin/env python3
"""执行 Week4 固定文本 workload，支持 /generate 与 /jobs。"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--mode", choices=("generate", "jobs"), required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--job-timeout-seconds", type=float, default=600.0)
    return parser.parse_args()


def request_json(method: str, url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(request, timeout=660.0) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw_error": raw}

def build_payload(record: dict) -> dict:
    prompt = record["prompt"]

    if "document_path" in record:
        document = Path(record["document_path"]).read_text(encoding="utf-8")
        prompt = document + record["prompt_suffix"]

    return {
        "prompt": prompt,
        "max_new_tokens": record.get("max_new_tokens", 128),
        "temperature": record.get("temperature", 0.0),
        "thinking_budget": record.get("thinking_budget", 0),
    }


def run_generate(base_url: str, payload: dict) -> tuple[int, dict, float]:
    started = time.perf_counter()
    status_code, body = request_json(
        "POST",
        f"{base_url}/generate",
        payload,
    )
    return status_code, body, time.perf_counter() - started


def run_job(
    base_url: str,
    payload: dict,
    poll_seconds: float,
    timeout_seconds: float,
) -> tuple[int | None, dict, float, float]:
    started = time.perf_counter()
    submit_started = time.perf_counter()

    submit_status, accepted = request_json(
        "POST",
        f"{base_url}/jobs",
        payload,
    )
    submit_latency = time.perf_counter() - submit_started

    if submit_status != 202:
        return submit_status, accepted, submit_latency, time.perf_counter() - started

    job_id = accepted["job_id"]
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        status_code, state = request_json(
            "GET",
            f"{base_url}/jobs/{job_id}",
        )

        if state.get("status") in {"succeeded", "failed"}:
            return status_code, state, submit_latency, time.perf_counter() - started

        time.sleep(poll_seconds)

    return None, {
        "job_id": job_id,
        "status": "poll_timeout",
        "error_message": f"job exceeded {timeout_seconds}s",
    }, submit_latency, time.perf_counter() - started
def _result_from_body(mode: str, body: dict) -> dict:
    if mode == "generate":
        return body
    result = body.get("result")
    return result if isinstance(result, dict) else {}


def main() -> None:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    manifest_path = Path(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    records_path = output_dir / "records.jsonl"
    codegen_responses_path = output_dir / "codegen_responses.jsonl"
    metrics_path = output_dir / "request_metrics.csv"
    summary_path = output_dir / "summary.json"

    records: list[dict] = []
    started_at = time.time()

    for index, source_record in enumerate(manifest_rows, start=1):
        case_id = source_record["case_id"]
        payload = build_payload(source_record)

        try:
            if args.mode == "generate":
                status_code, body, end_to_end_latency = run_generate(
                    base_url,
                    payload,
                )
                submit_latency = None
                service_status = (
                    "succeeded"
                    if 200 <= status_code < 300
                    else "failed"
                )
            else:
                status_code, body, submit_latency, end_to_end_latency = run_job(
                    base_url,
                    payload,
                    args.poll_seconds,
                    args.job_timeout_seconds,
                )
                service_status = body.get("status", "unknown")
        except Exception as exc:
            status_code = None
            body = {
                "status": "client_exception",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            submit_latency = None
            end_to_end_latency = 0.0
            service_status = "client_exception"

        result = _result_from_body(args.mode, body)
        generated_response = result.get("response")

        succeeded = (
            service_status == "succeeded"
            and isinstance(generated_response, str)
        )

        record = {
            "case_id": case_id,
            "scenario": source_record.get("scenario"),
            "mode": args.mode,
            "sequence": index,
            "http_status_code": status_code,
            "service_status": service_status,
            "succeeded": succeeded,
            "submit_latency_seconds": submit_latency,
            "end_to_end_latency_seconds": end_to_end_latency,
            "model_latency_seconds": result.get("latency_seconds"),
            "input_tokens": result.get("input_tokens"),
            "output_tokens": result.get("output_tokens"),
            "total_tokens": result.get("total_tokens"),
            "tokens_per_second": result.get("tokens_per_second"),
            "route": result.get("route"),
            "primary_attempts": result.get("primary_attempts"),
            "fallback_thinking_budget": result.get(
                "fallback_thinking_budget"
            ),
            "request_id": result.get("request_id"),
            "model_name": result.get("model_name"),
            "backend": result.get("backend"),
            "error_type": body.get("error_type"),
            "error_message": body.get("error_message"),
            "response": generated_response,
            "service_body": body,
        }
        records.append(record)

        if source_record.get("scenario") == "code_generation_functional":
            with codegen_responses_path.open(
                "a",
                encoding="utf-8",
            ) as response_file:
                response_file.write(
                    json.dumps(
                        {
                            "case_id": case_id,
                            "response": generated_response or "",
                            "succeeded": succeeded,
                            "http_status_code": status_code,
                            "service_status": service_status,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        print(
            json.dumps(
                {
                    "sequence": index,
                    "case_id": case_id,
                    "service_status": service_status,
                    "succeeded": succeeded,
                    "http_status_code": status_code,
                },
                ensure_ascii=False,
            )
        )

    with records_path.open("w", encoding="utf-8") as records_file:
        for record in records:
            records_file.write(
                json.dumps(record, ensure_ascii=False) + "\n"
            )

    csv_fields = [
        "case_id",
        "scenario",
        "mode",
        "sequence",
        "http_status_code",
        "service_status",
        "succeeded",
        "submit_latency_seconds",
        "end_to_end_latency_seconds",
        "model_latency_seconds",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "tokens_per_second",
        "route",
        "primary_attempts",
        "fallback_thinking_budget",
        "request_id",
        "model_name",
        "backend",
        "error_type",
        "error_message",
    ]
    with metrics_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(
            {field: record.get(field) for field in csv_fields}
            for record in records
        )

    outcome_counts: dict[str, int] = {}
    for record in records:
        status = record["service_status"]
        outcome_counts[status] = outcome_counts.get(status, 0) + 1

    summary = {
        "manifest": str(manifest_path),
        "mode": args.mode,
        "base_url": base_url,
        "started_at_epoch_seconds": started_at,
        "case_count": len(records),
        "succeeded": sum(record["succeeded"] for record in records),
        "failed": sum(not record["succeeded"] for record in records),
        "service_status_counts": outcome_counts,
        "artifacts": {
            "records_jsonl": str(records_path),
            "request_metrics_csv": str(metrics_path),
            "codegen_responses_jsonl": str(codegen_responses_path),
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()