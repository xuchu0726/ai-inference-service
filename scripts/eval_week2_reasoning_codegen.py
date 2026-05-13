import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8000/generate"


GSM8K_CASES = [
    {
        "case_id": "gsm8k_001",
        "task_type": "math_reasoning",
        "prompt": "小明有12个苹果，给了小红3个，又买了8个。现在小明有多少个苹果？请给出简短推理过程。",
        "expected_answer": "17",
    },
    {
        "case_id": "gsm8k_002",
        "task_type": "math_reasoning",
        "prompt": "一本书有120页，小李每天读15页。读完这本书需要多少天？请给出简短推理过程。",
        "expected_answer": "8",
    },
    {
        "case_id": "gsm8k_003",
        "task_type": "math_reasoning",
        "prompt": "一个班有36名学生，其中三分之一参加篮球队。参加篮球队的学生有多少人？请给出简短推理过程。",
        "expected_answer": "12",
    },
    {
        "case_id": "gsm8k_004",
        "task_type": "math_reasoning",
        "prompt": "商店里一支笔卖4元，小王买了7支，付了50元，应找回多少钱？请给出简短推理过程。",
        "expected_answer": "22",
    },
    {
        "case_id": "gsm8k_005",
        "task_type": "math_reasoning",
        "prompt": "一辆车每小时行驶60公里，2.5小时行驶多少公里？请给出简短推理过程。",
        "expected_answer": "150",
    },
]


CODE_CASES = [
    {
        "case_id": "code_001",
        "task_type": "code_generation",
        "prompt": "请用 Python 写一个函数 is_palindrome(s)，判断字符串去除空格并忽略大小写后是否为回文。只输出代码和简短说明。",
        "expected_answer": "is_palindrome",
    },
    {
        "case_id": "code_002",
        "task_type": "code_generation",
        "prompt": "请用 Python 写一个函数 top_k_frequent(nums, k)，返回列表中出现频率最高的 k 个元素。只输出代码和简短说明。",
        "expected_answer": "top_k_frequent",
    },
    {
        "case_id": "code_003",
        "task_type": "code_generation",
        "prompt": "下面代码有什么 bug？请修复：def avg(xs): return sum(xs) / len(x)。只输出修复后的代码和原因。",
        "expected_answer": "len(xs)",
    },
    {
        "case_id": "code_004",
        "task_type": "code_generation",
        "prompt": "请用 Python 写一个 FastAPI GET /health 接口，返回 {'status': 'ok'}。只输出代码。",
        "expected_answer": "FastAPI",
    },
    {
        "case_id": "code_005",
        "task_type": "code_generation",
        "prompt": "请用 Python 写一个函数 safe_divide(a, b)，当 b 为 0 时返回 None，否则返回 a / b。只输出代码。",
        "expected_answer": "safe_divide",
    },
]


def post_generate(
    url: str,
    case: dict[str, str],
    max_new_tokens: int,
    temperature: float,
    thinking_budget: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "prompt": case["prompt"],
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
            latency = time.time() - start
            status_code = response.status
            data = json.loads(raw_body)

        generated = str(data.get("response", ""))
        expected = case.get("expected_answer", "")
        contains_expected = expected.lower() in generated.lower()

        return {
            "case_id": case["case_id"],
            "task_type": case["task_type"],
            "status_code": status_code,
            "ok": True,
            "contains_expected": contains_expected,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": data.get("latency_seconds"),
            "backend": data.get("backend"),
            "model_name": data.get("model_name"),
            "device": data.get("device"),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "tokens_per_second": data.get("tokens_per_second"),
            "thinking_budget": thinking_budget,
            "expected_answer": expected,
            "response": generated,
            "error": "",
        }

    except urllib.error.HTTPError as exc:
        latency = time.time() - start
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "case_id": case["case_id"],
            "task_type": case["task_type"],
            "status_code": exc.code,
            "ok": False,
            "contains_expected": False,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "thinking_budget": thinking_budget,
            "expected_answer": case.get("expected_answer", ""),
            "response": "",
            "error": error_body[:1000],
        }

    except Exception as exc:
        latency = time.time() - start
        return {
            "case_id": case["case_id"],
            "task_type": case["task_type"],
            "status_code": None,
            "ok": False,
            "contains_expected": False,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "thinking_budget": thinking_budget,
            "expected_answer": case.get("expected_answer", ""),
            "response": "",
            "error": repr(exc)[:1000],
        }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "case_id",
        "task_type",
        "status_code",
        "ok",
        "contains_expected",
        "client_latency_seconds",
        "server_latency_seconds",
        "backend",
        "model_name",
        "device",
        "input_tokens",
        "output_tokens",
        "tokens_per_second",
        "thinking_budget",
        "expected_answer",
        "response",
        "error",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Seed-OSS service on small GSM8K-style and code generation tasks."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="results/week2_reasoning_codegen_eval.csv")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument(
        "--mode",
        choices=["all", "gsm8k", "code"],
        default="all",
    )

    args = parser.parse_args()

    cases: list[dict[str, str]] = []
    if args.mode in ("all", "gsm8k"):
        cases.extend(GSM8K_CASES)
    if args.mode in ("all", "code"):
        cases.extend(CODE_CASES)

    rows = []

    print("===== Week2 reasoning/codegen eval =====")
    print(f"url: {args.url}")
    print(f"mode: {args.mode}")
    print(f"cases: {len(cases)}")
    print(f"output: {args.output}")

    for case in cases:
        row = post_generate(
            url=args.url,
            case=case,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            thinking_budget=args.thinking_budget,
            timeout_seconds=args.timeout_seconds,
        )
        rows.append(row)
        print(
            f"case_id={row['case_id']} "
            f"task_type={row['task_type']} "
            f"ok={row['ok']} "
            f"contains_expected={row['contains_expected']} "
            f"latency={row['client_latency_seconds']} "
            f"tokens/s={row['tokens_per_second']}"
        )

    output_path = Path(args.output)
    write_csv(output_path, rows)

    success = [r for r in rows if r["ok"]]
    expected_hits = [r for r in rows if r["contains_expected"]]

    print()
    print(f"saved_csv: {output_path}")
    print(f"total_cases: {len(rows)}")
    print(f"successful_cases: {len(success)}")
    print(f"contains_expected_cases: {len(expected_hits)}")


if __name__ == "__main__":
    main()
