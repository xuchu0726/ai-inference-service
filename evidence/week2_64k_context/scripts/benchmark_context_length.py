import argparse
import csv
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8000/generate"


def build_prompt(target_chars: int) -> str:
    base = (
        "以下是一份用于长上下文推理服务测试的模拟合同文本。"
        "请在阅读后总结其中的价格风险、解除风险、责任风险、数据风险和合规风险。\n\n"
        "合同条款：甲方有权根据市场情况调整服务价格，乙方应在收到通知后继续履行合同。"
        "如乙方提前解除合同，应承担违约责任。甲方可以基于服务稳定性、安全合规和业务连续性需要，"
        "对服务内容、访问权限、数据处理流程和计费方式进行调整。乙方应保证提交数据来源合法，"
        "不得上传违反法律法规、侵犯第三方权益或包含敏感信息的数据。双方应对商业秘密和用户数据承担保密义务。\n\n"
    )

    chunks = []
    while len("".join(chunks)) < target_chars:
        chunks.append(base)

    text = "".join(chunks)[:target_chars]

    return (
        "请阅读下面的长文本合同材料，并输出结构化风险摘要。"
        "请按价格风险、解除风险、责任风险、数据风险、合规风险五类总结。\n\n"
        f"{text}"
    )


def post_generate(
    url: str,
    case_id: int,
    context_target: str,
    target_chars: int,
    prompt: str,
    max_new_tokens: int,
    temperature: float,
    thinking_budget: int,
    timeout_seconds: float,
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
            latency = time.time() - start
            status_code = response.status
            data = json.loads(raw_body)

        return {
            "case_id": case_id,
            "context_target": context_target,
            "target_chars": target_chars,
            "actual_input_chars": len(prompt),
            "status_code": status_code,
            "ok": True,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": data.get("latency_seconds"),
            "backend": data.get("backend"),
            "model_name": data.get("model_name"),
            "device": data.get("device"),
            "input_tokens": data.get("input_tokens"),
            "output_tokens": data.get("output_tokens"),
            "tokens_per_second": data.get("tokens_per_second"),
            "max_new_tokens": data.get("max_new_tokens", max_new_tokens),
            "thinking_budget": thinking_budget,
            "response_preview": str(data.get("response", ""))[:500],
            "error": "",
        }

    except urllib.error.HTTPError as exc:
        latency = time.time() - start
        error_body = exc.read().decode("utf-8", errors="replace")
        return {
            "case_id": case_id,
            "context_target": context_target,
            "target_chars": target_chars,
            "actual_input_chars": len(prompt),
            "status_code": exc.code,
            "ok": False,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "max_new_tokens": max_new_tokens,
            "thinking_budget": thinking_budget,
            "response_preview": "",
            "error": error_body[:1000],
        }

    except Exception as exc:
        latency = time.time() - start
        return {
            "case_id": case_id,
            "context_target": context_target,
            "target_chars": target_chars,
            "actual_input_chars": len(prompt),
            "status_code": None,
            "ok": False,
            "client_latency_seconds": round(latency, 6),
            "server_latency_seconds": None,
            "backend": "",
            "model_name": "",
            "device": "",
            "input_tokens": None,
            "output_tokens": None,
            "tokens_per_second": None,
            "max_new_tokens": max_new_tokens,
            "thinking_budget": thinking_budget,
            "response_preview": "",
            "error": repr(exc)[:1000],
        }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "case_id",
        "context_target",
        "target_chars",
        "actual_input_chars",
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
        "response_preview",
        "error",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark FastAPI /generate with synthetic long-context prompts."
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="results/week2_context_length_benchmark.csv")
    parser.add_argument(
        "--context-targets",
        default="4k,8k,16k,32k",
        help="Comma-separated context targets. Supported labels are mapped by --chars-per-target.",
    )
    parser.add_argument(
        "--chars-per-target",
        default="4k:12000,8k:24000,16k:48000,32k:96000,64k:192000",
        help="Mapping from target label to approximate input character count.",
    )
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--thinking-budget", type=int, default=512)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)

    args = parser.parse_args()

    char_map: dict[str, int] = {}
    for item in args.chars_per_target.split(","):
        key, value = item.split(":")
        char_map[key.strip()] = int(value.strip())

    targets = [x.strip() for x in args.context_targets.split(",") if x.strip()]

    rows: list[dict[str, Any]] = []

    print("===== CONTEXT LENGTH BENCHMARK CONFIG =====")
    print(f"url: {args.url}")
    print(f"output: {args.output}")
    print(f"context_targets: {targets}")
    print(f"max_new_tokens: {args.max_new_tokens}")
    print(f"thinking_budget: {args.thinking_budget}")
    print(f"timeout_seconds: {args.timeout_seconds}")

    for case_id, target in enumerate(targets, start=1):
        if target not in char_map:
            raise ValueError(f"Unknown context target {target}. Available: {sorted(char_map)}")

        target_chars = char_map[target]
        prompt = build_prompt(target_chars)

        print()
        print(f"===== running context target {target} target_chars={target_chars} =====")

        row = post_generate(
            url=args.url,
            case_id=case_id,
            context_target=target,
            target_chars=target_chars,
            prompt=prompt,
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            thinking_budget=args.thinking_budget,
            timeout_seconds=args.timeout_seconds,
        )
        rows.append(row)

        print(
            f"context={target} "
            f"ok={row['ok']} "
            f"status={row['status_code']} "
            f"latency={row['client_latency_seconds']} "
            f"input_tokens={row['input_tokens']} "
            f"output_tokens={row['output_tokens']} "
            f"tokens/s={row['tokens_per_second']}"
        )

    output_path = Path(args.output)
    write_csv(output_path, rows)
    print()
    print(f"saved_csv: {output_path}")


if __name__ == "__main__":
    main()
