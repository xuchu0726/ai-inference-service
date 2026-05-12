import argparse
import csv
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8000/generate"

PROMPTS = [
    {
        "prompt_id": "llm_inference_cn",
        "prompt": "请用三句话解释什么是大模型推理，并说明为什么 vLLM 适合做推理服务。",
    },
    {
        "prompt_id": "legal_summary_cn",
        "prompt": "请总结下面这段法律文本的核心风险点：甲方有权单方面修改服务价格，乙方不得提前解除合同，否则需支付违约金。",
    },
    {
        "prompt_id": "kv_cache_en",
        "prompt": "Explain KV Cache in LLM inference. Focus on latency, memory usage, and long-context serving.",
    },
    {
        "prompt_id": "seed_oss_planning_cn",
        "prompt": "请从 AI 推理工程角度说明部署 36B 大模型时为什么需要多 GPU、KV Cache 管理和性能压测。",
    },
]


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def post_generate(
    url: str,
    case_id: int,
    prompt_id: str,
    prompt: str,
    thinking_budget: int,
    max_new_tokens: int,
    temperature: float,
    timeout_seconds: float,
    concurrency: int,
) -> dict[str, Any]:
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

    start = time.time()

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_body = response.read().decode("utf-8")
            client_latency = time.time() - start
            status_code = response.status
            data = json.loads(raw_body)

        return {
            "case_id": case_id,
            "prompt_id": prompt_id,
            "thinking_budget": thinking_budget,
            "concurrency": concurrency,
            "status_code": status_code,
            "ok": True,
            "client_latency_seconds": round(client_latency, 6),
            "server_latency_seconds": data.get("latency_seconds"),
            "backend": data.get("backend"),
            "model_name": data.get("model_name"),
            "device": data.get("device"),
            "input_chars": data.get("input_chars"),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "tokens_per_second": data.get("tokens_per_second"),
            "max_new_tokens": data.get("max_new_tokens", max_new_tokens),
            "response": data.get("response", ""),
            "error": "",
        }

    except urllib.error.HTTPError as exc:
        client_latency = time.time() - start
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "case_id": case_id,
            "prompt_id": prompt_id,
            "thinking_budget": thinking_budget,
            "concurrency": concurrency,
            "status_code": exc.code,
            "ok": False,
            "client_latency_seconds": round(client_latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_chars": len(prompt),
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "max_new_tokens": max_new_tokens,
            "response": "",
            "error": error_body[:1000],
        }

    except Exception as exc:
        client_latency = time.time() - start
        return {
            "case_id": case_id,
            "prompt_id": prompt_id,
            "thinking_budget": thinking_budget,
            "concurrency": concurrency,
            "status_code": None,
            "ok": False,
            "client_latency_seconds": round(client_latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_chars": len(prompt),
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "max_new_tokens": max_new_tokens,
            "response": "",
            "error": repr(exc)[:1000],
        }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "case_id",
        "prompt_id",
        "thinking_budget",
        "concurrency",
        "benchmark_wall_time_seconds",
        "throughput_qps",
        "status_code",
        "ok",
        "client_latency_seconds",
        "server_latency_seconds",
        "backend",
        "model_name",
        "device",
        "input_chars",
        "input_tokens",
        "output_tokens",
        "tokens_per_second",
        "max_new_tokens",
        "response",
        "error",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    success = [r for r in rows if r["ok"]]
    failed = [r for r in rows if not r["ok"]]

    latencies = [
        float(r["client_latency_seconds"])
        for r in success
        if r.get("client_latency_seconds") is not None
    ]

    tokens_per_second = [
        float(r["tokens_per_second"])
        for r in success
        if r.get("tokens_per_second") is not None
    ]

    wall_times = [
        float(r["benchmark_wall_time_seconds"])
        for r in rows
        if r.get("benchmark_wall_time_seconds") is not None
    ]
    qps_values = [
        float(r["throughput_qps"])
        for r in rows
        if r.get("throughput_qps") is not None
    ]

    print("===== VLLM BACKEND BENCHMARK SUMMARY =====")
    if wall_times:
        print(f"benchmark_wall_time_seconds: {round(max(wall_times), 6)}")
    if qps_values:
        print(f"throughput_qps: {round(max(qps_values), 6)}")
    print(f"total_requests: {total}")
    print(f"successful_requests: {len(success)}")
    print(f"failed_requests: {len(failed)}")
    print(f"error_rate: {round(len(failed) / total, 6) if total else None}")

    if latencies:
        print(f"client_latency_avg: {round(statistics.mean(latencies), 6)}")
        print(f"client_latency_p50: {round(percentile(latencies, 0.50), 6)}")
        print(f"client_latency_p95: {round(percentile(latencies, 0.95), 6)}")

    if tokens_per_second:
        print(f"tokens_per_second_avg: {round(statistics.mean(tokens_per_second), 6)}")
        print(f"tokens_per_second_p50: {round(percentile(tokens_per_second, 0.50), 6)}")
        print(f"tokens_per_second_p95: {round(percentile(tokens_per_second, 0.95), 6)}")

    print()
    print("Note: this benchmark calls the non-streaming /generate API.")
    print("TTFT requires a streaming endpoint and will be implemented separately.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark FastAPI /generate with VLLMBackend."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="results/vllm_backend_benchmark.csv")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--thinking-budgets",
        default="128,512,1024",
        help="Comma-separated thinking budget values.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=300.0)

    args = parser.parse_args()

    budgets = [
        int(x.strip())
        for x in args.thinking_budgets.split(",")
        if x.strip()
    ]

    tasks: list[dict[str, Any]] = []
    case_id = 0

    for _ in range(args.repeat):
        for prompt_case in PROMPTS:
            for budget in budgets:
                case_id += 1
                tasks.append(
                    {
                        "case_id": case_id,
                        "prompt_id": prompt_case["prompt_id"],
                        "prompt": prompt_case["prompt"],
                        "thinking_budget": budget,
                    }
                )

    print("===== BENCHMARK CONFIG =====")
    print(f"url: {args.url}")
    print(f"output: {args.output}")
    print(f"concurrency: {args.concurrency}")
    print(f"repeat: {args.repeat}")
    print(f"max_new_tokens: {args.max_new_tokens}")
    print(f"temperature: {args.temperature}")
    print(f"thinking_budgets: {budgets}")
    print(f"total_requests: {len(tasks)}")

    rows: list[dict[str, Any]] = []

    benchmark_start = time.time()

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(
                post_generate,
                args.url,
                task["case_id"],
                task["prompt_id"],
                task["prompt"],
                task["thinking_budget"],
                args.max_new_tokens,
                args.temperature,
                args.timeout_seconds,
                args.concurrency,
            )
            for task in tasks
        ]

        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            print(
                f"case_id={row['case_id']} "
                f"ok={row['ok']} "
                f"status={row['status_code']} "
                f"latency={row['client_latency_seconds']} "
                f"backend={row['backend']} "
                f"tokens/s={row['tokens_per_second']}"
            )

    benchmark_wall_time = time.time() - benchmark_start
    throughput_qps = len(rows) / benchmark_wall_time if benchmark_wall_time > 0 else None

    for row in rows:
        row["benchmark_wall_time_seconds"] = round(benchmark_wall_time, 6)
        row["throughput_qps"] = round(throughput_qps, 6) if throughput_qps is not None else None

    rows.sort(key=lambda x: x["case_id"])
    output_path = Path(args.output)
    write_csv(output_path, rows)

    print()
    print(f"saved_csv: {output_path}")
    print_summary(rows)


if __name__ == "__main__":
    main()
