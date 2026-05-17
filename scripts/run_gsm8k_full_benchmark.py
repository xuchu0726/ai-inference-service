#!/usr/bin/env python3
"""
Full GSM8K benchmark runner for the Week2 Seed-OSS inference service.

This script evaluates the FastAPI /generate endpoint on GSM8K test data and records:
- per-case API status
- client/server latency
- input/output tokens
- tokens/s
- predicted final answer
- correctness
- response preview
- error message

It supports:
- local GSM8K JSONL input
- optional download of the standard GSM8K test JSONL
- resume mode
- full benchmark by default
- optional --limit for smoke/debug runs

No third-party Python packages are required.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import time
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


DEFAULT_GSM8K_TEST_URL = (
    "https://huggingface.co/datasets/openai/gsm8k/resolve/main/main/test.jsonl"
)


def download_if_missing(path: Path, url: str) -> None:
    if path.exists():
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"dataset_missing: {path}")
    print(f"downloading: {url}")

    request = urllib.request.Request(url, headers={"User-Agent": "week2-gsm8k-runner"})
    with urllib.request.urlopen(request, timeout=120) as response:
        content = response.read()

    path.write_bytes(content)
    print(f"saved_dataset: {path} bytes={len(content)}")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            raw = json.loads(line)

            question = str(raw.get("question", "")).strip()
            answer_field = str(raw.get("answer", "")).strip()

            expected = extract_expected_answer(raw)
            case_id = str(raw.get("case_id", f"gsm8k_{idx:04d}"))

            if not question:
                raise ValueError(f"missing question at line {idx}")
            if expected == "":
                raise ValueError(f"missing expected answer at line {idx}")

            rows.append(
                {
                    "case_id": case_id,
                    "question": question,
                    "answer": answer_field,
                    "expected_answer": expected,
                }
            )

    return rows


def extract_expected_answer(row: dict[str, Any]) -> str:
    if "expected_answer" in row:
        return normalize_number_string(str(row["expected_answer"]))

    answer = str(row.get("answer", ""))

    # GSM8K official format usually ends with "#### 42".
    marker_match = re.search(r"####\s*([-+]?\$?\d[\d,]*(?:\.\d+)?)", answer)
    if marker_match:
        return normalize_number_string(marker_match.group(1))

    numbers = re.findall(r"[-+]?\$?\d[\d,]*(?:\.\d+)?", answer)
    if numbers:
        return normalize_number_string(numbers[-1])

    return ""


def normalize_number_string(text: str) -> str:
    value = text.strip()
    value = value.replace("$", "")
    value = value.replace(",", "")
    value = value.rstrip(".")
    return value


def to_decimal_or_none(value: str) -> Decimal | None:
    value = normalize_number_string(value)
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def extract_predicted_answer(response_text: str) -> str:
    if not response_text:
        return ""

    patterns = [
        r"Final answer\s*[:：]\s*([-+]?\$?\d[\d,]*(?:\.\d+)?)",
        r"final answer\s*[:：]\s*([-+]?\$?\d[\d,]*(?:\.\d+)?)",
        r"答案\s*[:：]\s*([-+]?\$?\d[\d,]*(?:\.\d+)?)",
        r"最终答案\s*[:：]\s*([-+]?\$?\d[\d,]*(?:\.\d+)?)",
    ]

    for pattern in patterns:
        match = re.search(pattern, response_text, flags=re.IGNORECASE)
        if match:
            return normalize_number_string(match.group(1))

    # Fallback: use the last number in the response.
    numbers = re.findall(r"[-+]?\$?\d[\d,]*(?:\.\d+)?", response_text)
    if numbers:
        return normalize_number_string(numbers[-1])

    return ""


def is_correct(expected: str, predicted: str) -> bool:
    expected_dec = to_decimal_or_none(expected)
    predicted_dec = to_decimal_or_none(predicted)

    if expected_dec is not None and predicted_dec is not None:
        return expected_dec == predicted_dec

    return normalize_number_string(expected) == normalize_number_string(predicted)


def build_prompt(question: str) -> str:
    return (
        "Solve the following grade-school math problem. "
        "Show concise reasoning. "
        "End your response exactly with the format: Final answer: <number>.\n\n"
        f"Problem: {question}"
    )


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


def read_completed_case_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()

    completed: set[str] = set()

    with output_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_id = str(row.get("case_id", "")).strip()
            if case_id:
                completed.add(case_id)

    return completed


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0

    values_sorted = sorted(values)
    if len(values_sorted) == 1:
        return values_sorted[0]

    rank = (len(values_sorted) - 1) * p
    lower = int(rank)
    upper = min(lower + 1, len(values_sorted) - 1)
    weight = rank - lower

    return values_sorted[lower] * (1 - weight) + values_sorted[upper] * weight


def write_summary(output_path: Path, summary_path: Path) -> None:
    if not output_path.exists():
        raise FileNotFoundError(output_path)

    rows: list[dict[str, str]] = []

    with output_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows.extend(reader)

    total = len(rows)
    successful_api = [r for r in rows if r.get("ok") == "True"]
    correct_rows = [r for r in rows if r.get("correct") == "True"]
    parseable_rows = [r for r in rows if r.get("predicted_answer", "") != ""]

    client_latencies = [
        float(r["client_latency_seconds"])
        for r in successful_api
        if r.get("client_latency_seconds")
    ]

    server_latencies = [
        float(r["server_latency_seconds"])
        for r in successful_api
        if r.get("server_latency_seconds")
    ]

    tokens_per_second = [
        float(r["tokens_per_second"])
        for r in successful_api
        if r.get("tokens_per_second")
    ]

    output_tokens = [
        float(r["output_tokens"])
        for r in successful_api
        if r.get("output_tokens")
    ]

    summary_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "total_cases": total,
        "successful_api_cases": len(successful_api),
        "failed_api_cases": total - len(successful_api),
        "api_error_rate": round((total - len(successful_api)) / total, 6) if total else 0,
        "parseable_answer_cases": len(parseable_rows),
        "correct_cases": len(correct_rows),
        "accuracy_all_cases": round(len(correct_rows) / total, 6) if total else 0,
        "accuracy_successful_api_cases": round(len(correct_rows) / len(successful_api), 6)
        if successful_api
        else 0,
        "client_latency_avg": round(statistics.mean(client_latencies), 6)
        if client_latencies
        else 0,
        "client_latency_p50": round(percentile(client_latencies, 0.50), 6)
        if client_latencies
        else 0,
        "client_latency_p95": round(percentile(client_latencies, 0.95), 6)
        if client_latencies
        else 0,
        "server_latency_avg": round(statistics.mean(server_latencies), 6)
        if server_latencies
        else 0,
        "server_latency_p50": round(percentile(server_latencies, 0.50), 6)
        if server_latencies
        else 0,
        "server_latency_p95": round(percentile(server_latencies, 0.95), 6)
        if server_latencies
        else 0,
        "tokens_per_second_avg": round(statistics.mean(tokens_per_second), 6)
        if tokens_per_second
        else 0,
        "tokens_per_second_p50": round(percentile(tokens_per_second, 0.50), 6)
        if tokens_per_second
        else 0,
        "tokens_per_second_p95": round(percentile(tokens_per_second, 0.95), 6)
        if tokens_per_second
        else 0,
        "output_tokens_avg": round(statistics.mean(output_tokens), 6)
        if output_tokens
        else 0,
    }

    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)

    print("===== GSM8K SUMMARY =====")
    for key, value in summary.items():
        print(f"{key}: {value}")

    print(f"saved_summary: {summary_path}")


def run_benchmark(args: argparse.Namespace) -> None:
    dataset_path = Path(args.dataset)

    if args.download_if_missing:
        download_if_missing(dataset_path, args.dataset_url)

    rows = load_jsonl(dataset_path)

    if args.limit is not None:
        rows = rows[: args.limit]

    output_path = Path(args.output)
    summary_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed = read_completed_case_ids(output_path) if args.resume else set()

    fieldnames = [
        "case_id",
        "status_code",
        "ok",
        "correct",
        "expected_answer",
        "predicted_answer",
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
        "question_preview",
        "response_preview",
        "error",
    ]

    file_exists = output_path.exists() and args.resume

    with output_path.open("a" if file_exists else "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for idx, row in enumerate(rows, start=1):
            case_id = str(row["case_id"])

            if case_id in completed:
                print(f"skip_completed: {case_id}")
                continue

            prompt = build_prompt(row["question"])

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

            predicted_answer = extract_predicted_answer(response_text)
            correct = is_correct(row["expected_answer"], predicted_answer)

            record = {
                "case_id": case_id,
                "status_code": status_code,
                "ok": bool(result is not None and 200 <= status_code < 300),
                "correct": correct if result is not None else False,
                "expected_answer": row["expected_answer"],
                "predicted_answer": predicted_answer,
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
                "question_preview": row["question"][:200].replace("\n", "\\n"),
                "response_preview": response_text[:500].replace("\n", "\\n"),
                "error": error[:500].replace("\n", "\\n"),
            }

            writer.writerow(record)
            f.flush()

            print(
                f"[{idx}/{len(rows)}] {case_id} "
                f"status={status_code} "
                f"ok={record['ok']} "
                f"expected={record['expected_answer']} "
                f"predicted={record['predicted_answer']} "
                f"correct={record['correct']} "
                f"latency={client_latency:.3f}s"
            )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    write_summary(output_path, summary_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("--url", default="http://127.0.0.1:8000/generate")
    parser.add_argument("--dataset", default="data/eval/gsm8k_test.jsonl")
    parser.add_argument("--dataset-url", default=DEFAULT_GSM8K_TEST_URL)
    parser.add_argument("--download-if-missing", action="store_true")

    parser.add_argument("--output", default="results/week2_gsm8k_full_seed_oss.csv")
    parser.add_argument(
        "--summary-output",
        default="results/week2_gsm8k_full_seed_oss_summary.csv",
    )

    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=1800)

    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--resume", action="store_true")

    return parser.parse_args()


if __name__ == "__main__":
    run_benchmark(parse_args())
