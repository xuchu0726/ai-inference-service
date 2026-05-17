#!/usr/bin/env python3
"""
Week2 mini evaluation runner for Seed-OSS inference service.

This script calls the FastAPI /generate endpoint and records:
- API status
- client latency
- server latency
- backend/model/device
- input/output tokens
- tokens/s
- simple correctness check
- response preview

It is designed for short GPU windows and reproducible Week2 evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_prompt(task_type: str, row: dict[str, Any]) -> str:
    if task_type == "gsm8k":
        return (
            "Solve the following grade-school math problem. "
            "Show concise reasoning and end with 'Final answer: <number>'.\n\n"
            f"Problem: {row['question']}"
        )

    if task_type == "codegen":
        return (
            "Write clean Python code for the following task. "
            "Return only the code, with no long explanation.\n\n"
            f"Task: {row['task']}"
        )

    raise ValueError(f"Unsupported task_type: {task_type}")


def post_generate(
    url: str,
    prompt: str,
    max_new_tokens: int,
    temperature: float,
    thinking_budget: int,
    timeout_seconds: float,
) -> tuple[int, float, dict[str, Any] | None, str]:
    payload = {
        "prompt": prompt,
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
        "thinking_budget": thinking_budget,
    }

    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            client_latency = time.perf_counter() - start
            body = response.read().decode("utf-8")
            return response.status, client_latency, json.loads(body), ""
    except urllib.error.HTTPError as exc:
        client_latency = time.perf_counter() - start
        error_body = exc.read().decode("utf-8", errors="replace")
        return exc.code, client_latency, None, error_body
    except Exception as exc:
        client_latency = time.perf_counter() - start
        return 0, client_latency, None, repr(exc)


def simple_correctness(task_type: str, row: dict[str, Any], response_text: str) -> str:
    if not response_text:
        return "empty"

    if task_type == "gsm8k":
        expected = str(row.get("expected_answer", "")).strip()
        if expected and expected in response_text:
            return "pass"
        return "manual_check"

    if task_type == "codegen":
        expected_keywords = row.get("expected_keywords", [])
        if all(str(keyword) in response_text for keyword in expected_keywords):
            return "pass"
        return "manual_check"

    return "manual_check"


def run_eval(args: argparse.Namespace) -> None:
    rows = load_jsonl(Path(args.dataset))
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "case_id",
        "task_type",
        "status_code",
        "ok",
        "client_latency_seconds",
        "server_latency_seconds",
        "backend",
        "model_name",
        "device",
        "input_tokens",
        "output_tokens",
        "tokens_per_second",
        "max_new_tokens",
        "thinking_budget",
        "simple_correctness",
        "response_preview",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            prompt = build_prompt(args.task_type, row)

            status_code, client_latency, result, error = post_generate(
                url=args.url,
                prompt=prompt,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
                thinking_budget=args.thinking_budget,
                timeout_seconds=args.timeout_seconds,
            )

            response_text = ""
            if result is not None:
                response_text = str(result.get("response", ""))

            correctness = simple_correctness(args.task_type, row, response_text)

            record = {
                "case_id": row.get("case_id", ""),
                "task_type": args.task_type,
                "status_code": status_code,
                "ok": bool(result is not None and 200 <= status_code < 300),
                "client_latency_seconds": round(client_latency, 6),
                "server_latency_seconds": result.get("latency_seconds", "") if result else "",
                "backend": result.get("backend", "") if result else "",
                "model_name": result.get("model_name", "") if result else "",
                "device": result.get("device", "") if result else "",
                "input_tokens": result.get("input_tokens", "") if result else "",
                "output_tokens": result.get("output_tokens", "") if result else "",
                "tokens_per_second": result.get("tokens_per_second", "") if result else "",
                "max_new_tokens": args.max_new_tokens,
                "thinking_budget": args.thinking_budget,
                "simple_correctness": correctness,
                "response_preview": response_text[:300].replace("\n", "\\n"),
                "error": error[:300].replace("\n", "\\n"),
            }

            writer.writerow(record)

            print(
                f"{record['case_id']} "
                f"status={status_code} "
                f"ok={record['ok']} "
                f"latency={client_latency:.3f}s "
                f"correctness={correctness}"
            )

    print(f"saved_csv: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/generate")
    parser.add_argument("--task-type", choices=["gsm8k", "codegen"], required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    return parser.parse_args()


if __name__ == "__main__":
    run_eval(parse_args())
