#!/usr/bin/env python3
"""
Seed-OSS-36B BitsAndBytes LLM.int8() batched GSM8K evaluator.

用途：
- 不调用 FastAPI；
- 不修改 app/ 下的单请求服务；
- 直接加载本地 Seed-OSS + BnB LLM.int8；
- 采用静态 batch 批量生成；
- 复用现有 GSM8K prompt、答案提取和 exact-match 规则；
- 支持与串行 reference CSV 逐题比较。
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
import traceback
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from run_gsm8k_full_benchmark import (
    build_prompt,
    extract_predicted_answer,
    is_correct,
    load_jsonl,
    percentile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--model-path",
        default="/workspace/models/Seed-OSS-36B-Instruct",
    )
    parser.add_argument(
        "--dataset",
        default="data/eval/gsm8k_test.jsonl",
    )
    parser.add_argument(
        "--output",
        required=True,
    )
    parser.add_argument(
        "--summary-output",
        required=True,
    )
    parser.add_argument(
        "--reference",
        default="",
        help="可选：串行 reference CSV，用于逐题一致性比较。",
    )
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--resume", action="store_true")

    return parser.parse_args()


def load_completed_case_ids(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()

    completed: set[str] = set()

    with output_path.open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            case_id = str(row.get("case_id", "")).strip()
            if case_id:
                completed.add(case_id)

    return completed


def load_reference(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"reference CSV not found: {path}")

    with path.open(encoding="utf-8", newline="") as file:
        return {
            row["case_id"]: row
            for row in csv.DictReader(file)
            if row.get("case_id")
        }


def make_formatted_prompt(
    tokenizer: Any,
    question: str,
    thinking_budget: int,
) -> str:
    prompt = build_prompt(question)

    return tokenizer.apply_chat_template(
        [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        tokenize=False,
        add_generation_prompt=True,
        thinking_budget=thinking_budget,
    )


def get_memory_snapshot() -> dict[str, dict[str, float]]:
    return {
        f"cuda:{index}": {
            "allocated_gib": round(
                torch.cuda.memory_allocated(index) / 1024**3,
                3,
            ),
            "reserved_gib": round(
                torch.cuda.memory_reserved(index) / 1024**3,
                3,
            ),
            "peak_allocated_gib": round(
                torch.cuda.max_memory_allocated(index) / 1024**3,
                3,
            ),
        }
        for index in range(torch.cuda.device_count())
    }


def write_summary(
    output_path: Path,
    summary_path: Path,
    batch_size: int,
    reference_path: str,
) -> None:
    with output_path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))

    total_cases = len(rows)
    successful_rows = [row for row in rows if row["ok"] == "True"]
    correct_rows = [row for row in rows if row["correct"] == "True"]

    batch_latencies = [
        float(row["batch_latency_seconds"])
        for row in successful_rows
        if row.get("batch_latency_seconds")
    ]

    batch_output_tokens = [
        int(row["batch_total_output_tokens"])
        for row in successful_rows
        if row.get("batch_total_output_tokens")
    ]

    reference_mismatch_rows = [
        row
        for row in rows
        if row.get("reference_predicted_answer", "")
        and row["predicted_answer"] != row["reference_predicted_answer"]
    ]

    summary = {
        "total_cases": total_cases,
        "successful_cases": len(successful_rows),
        "failed_cases": total_cases - len(successful_rows),
        "accuracy": round(len(correct_rows) / total_cases, 6)
        if total_cases
        else 0,
        "batch_size": batch_size,
        "batch_latency_avg_seconds": round(statistics.mean(batch_latencies), 6)
        if batch_latencies
        else 0,
        "batch_latency_p50_seconds": round(percentile(batch_latencies, 0.50), 6)
        if batch_latencies
        else 0,
        "batch_latency_p95_seconds": round(percentile(batch_latencies, 0.95), 6)
        if batch_latencies
        else 0,
        "batch_total_output_tokens_avg": round(
            statistics.mean(batch_output_tokens),
            6,
        )
        if batch_output_tokens
        else 0,
        "reference_csv": reference_path,
        "reference_prediction_mismatch_cases": len(reference_mismatch_rows),
        "memory_snapshot": get_memory_snapshot(),
    }

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\n===== BATCHED GSM8K SUMMARY =====")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"saved_summary: {summary_path}")


def main() -> None:
    args = parse_args()

    if args.batch_size <= 0:
        raise ValueError("--batch-size must be positive")

    output_path = Path(args.output)
    summary_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(Path(args.dataset))
    if args.limit is not None:
        rows = rows[: args.limit]

    completed = load_completed_case_ids(output_path) if args.resume else set()
    rows = [row for row in rows if row["case_id"] not in completed]

    reference_rows: dict[str, dict[str, str]] = {}
    if args.reference:
        reference_rows = load_reference(Path(args.reference))

    print("正在加载 Seed-OSS-36B BitsAndBytes LLM.int8() 模型。")

    tokenizer = AutoTokenizer.from_pretrained(args.model_path)
    tokenizer.padding_side = "left"

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_threshold=6.0,
    )

    model_load_start = time.perf_counter()

    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        quantization_config=quantization_config,
        device_map="auto",
        dtype=torch.bfloat16,
        attn_implementation="eager",
        low_cpu_mem_usage=True,
    )

    model.eval()
    input_device = next(model.parameters()).device
    model_load_seconds = time.perf_counter() - model_load_start

    print(f"模型加载完成，耗时: {model_load_seconds:.3f} 秒")
    print(f"batch_size: {args.batch_size}")
    print(f"待评测样本数: {len(rows)}")
    print(f"输入设备: {input_device}")

    fieldnames = [
        "case_id",
        "ok",
        "correct",
        "expected_answer",
        "predicted_answer",
        "reference_predicted_answer",
        "reference_prediction_match",
        "batch_index",
        "batch_size_actual",
        "batch_latency_seconds",
        "batch_total_output_tokens",
        "batch_aggregate_tokens_per_second",
        "input_tokens_padded",
        "output_tokens",
        "question_preview",
        "response_preview",
        "error",
    ]

    file_exists = output_path.exists() and args.resume

    with output_path.open(
        "a" if file_exists else "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for batch_start in range(0, len(rows), args.batch_size):
            batch_rows = rows[batch_start : batch_start + args.batch_size]
            batch_number = batch_start // args.batch_size + 1

            formatted_prompts = [
                make_formatted_prompt(
                    tokenizer=tokenizer,
                    question=row["question"],
                    thinking_budget=args.thinking_budget,
                )
                for row in batch_rows
            ]

            try:
                encoded = tokenizer(
                    formatted_prompts,
                    padding=True,
                    return_tensors="pt",
                ).to(input_device)

                encoded.pop("token_type_ids", None)

                input_width = int(encoded["input_ids"].shape[1])
                batch_start_time = time.perf_counter()

                with torch.inference_mode():
                    generated = model.generate(
                        **encoded,
                        max_new_tokens=args.max_new_tokens,
                        do_sample=False,
                        use_cache=True,
                    )

                batch_latency = time.perf_counter() - batch_start_time
                generated_only = generated[:, input_width:]

                responses = tokenizer.batch_decode(
                    generated_only,
                    skip_special_tokens=True,
                )

                output_token_counts = [
                    len(
                        tokenizer.encode(
                            response,
                            add_special_tokens=False,
                        )
                    )
                    for response in responses
                ]

                batch_total_output_tokens = sum(output_token_counts)
                aggregate_tokens_per_second = (
                    batch_total_output_tokens / batch_latency
                    if batch_latency > 0
                    else 0
                )

                for row, response, output_tokens in zip(
                    batch_rows,
                    responses,
                    output_token_counts,
                    strict=True,
                ):
                    predicted_answer = extract_predicted_answer(response)
                    correct = is_correct(
                        row["expected_answer"],
                        predicted_answer,
                    )

                    reference = reference_rows.get(row["case_id"], {})
                    reference_prediction = reference.get(
                        "predicted_answer",
                        "",
                    )

                    record = {
                        "case_id": row["case_id"],
                        "ok": True,
                        "correct": correct,
                        "expected_answer": row["expected_answer"],
                        "predicted_answer": predicted_answer,
                        "reference_predicted_answer": reference_prediction,
                        "reference_prediction_match": (
                            predicted_answer == reference_prediction
                            if reference_prediction
                            else ""
                        ),
                        "batch_index": batch_number,
                        "batch_size_actual": len(batch_rows),
                        "batch_latency_seconds": round(batch_latency, 6),
                        "batch_total_output_tokens": batch_total_output_tokens,
                        "batch_aggregate_tokens_per_second": round(
                            aggregate_tokens_per_second,
                            6,
                        ),
                        "input_tokens_padded": input_width,
                        "output_tokens": output_tokens,
                        "question_preview": row["question"][:200].replace(
                            "\n",
                            "\\n",
                        ),
                        "response_preview": response[:500].replace(
                            "\n",
                            "\\n",
                        ),
                        "error": "",
                    }

                    writer.writerow(record)

                    print(
                        f"[{batch_start + 1}-{batch_start + len(batch_rows)}"
                        f"/{len(rows)}] "
                        f"{row['case_id']} "
                        f"expected={row['expected_answer']} "
                        f"predicted={predicted_answer} "
                        f"correct={correct} "
                        f"batch_tps={aggregate_tokens_per_second:.3f}"
                    )

                file.flush()

            except Exception as exc:
                error_text = (
                    f"{type(exc).__name__}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

                print(
                    f"batch_failed: "
                    f"{batch_start + 1}-{batch_start + len(batch_rows)} "
                    f"{type(exc).__name__}: {exc}"
                )

                for row in batch_rows:
                    writer.writerow(
                        {
                            "case_id": row["case_id"],
                            "ok": False,
                            "correct": False,
                            "expected_answer": row["expected_answer"],
                            "predicted_answer": "",
                            "reference_predicted_answer": "",
                            "reference_prediction_match": "",
                            "batch_index": batch_number,
                            "batch_size_actual": len(batch_rows),
                            "batch_latency_seconds": "",
                            "batch_total_output_tokens": "",
                            "batch_aggregate_tokens_per_second": "",
                            "input_tokens_padded": "",
                            "output_tokens": "",
                            "question_preview": row["question"][:200].replace(
                                "\n",
                                "\\n",
                            ),
                            "response_preview": "",
                            "error": error_text[:1500].replace("\n", "\\n"),
                        }
                    )

                file.flush()
                raise

    write_summary(
        output_path=output_path,
        summary_path=summary_path,
        batch_size=args.batch_size,
        reference_path=args.reference,
    )


if __name__ == "__main__":
    main()
