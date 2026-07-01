#!/usr/bin/env python3
"""生成 Week4 固定 workload bundle，并校验可复现性。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "data" / "week4_workloads"
BAGEL_CASE_DIR = ROOT / "data" / "week3_bagel" / "cases"
CODEGEN_SOURCE = ROOT / "data" / "eval" / "codegen_mini.jsonl"


def write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_customer_service() -> list[dict[str, object]]:
    prompts = [
        "我的订单显示已签收，但我没有收到包裹。请说明我现在可以做什么。",
        "我想取消刚刚提交的订单，但页面没有取消按钮。请给出处理步骤。",
        "商品到货后发现颜色与页面展示不一致，我可以申请退货吗？",
        "我的退款申请已经提交三天了，如何查看处理进度？",
        "支付页面提示扣款成功，但订单列表中没有订单记录，应该怎么办？",
        "我忘记了账号密码，无法登录。请告诉我如何安全地重置密码。",
        "配送地址填写错误，但订单还没有发货。请说明修改地址的处理方式。",
        "我收到的商品缺少一个配件。请问需要准备哪些信息申请补发？",
        "优惠券在结算页面无法使用。请说明需要检查哪些常见原因。",
        "同一笔订单被重复扣款两次，我该如何提交问题说明？",
        "我想查询发票开具状态，并了解需要提供哪些订单信息。",
        "商品页面写着支持七天无理由退货，但我的商品已经拆封，是否还能申请？",
    ]

    return [
        {
            "case_id": f"customer_service_{index:03d}",
            "scenario": "customer_service",
            "prompt": (
                "你是电商客服助手。请用中文回答用户问题。"
                "仅给出可执行步骤；不要编造订单状态、退款金额、物流信息或平台政策细节。"
                f"\n\n用户问题：{prompt}"
            ),
            "max_new_tokens": 128,
            "temperature": 0.0,
            "thinking_budget": 0,
        }
        for index, prompt in enumerate(prompts, start=1)
    ]


def build_codegen() -> list[dict[str, object]]:
    records: list[dict[str, object]] = []

    for line in CODEGEN_SOURCE.read_text(encoding="utf-8").splitlines():
        source = json.loads(line)
        records.append(
            {
                "case_id": source["case_id"],
                "scenario": "code_generation",
                "source_dataset": "data/eval/codegen_mini.jsonl",
                "prompt": (
                    "Return only valid Python code in one code block.\n\n"
                    + source["task"]
                ),
                "expected_keywords": source["expected_keywords"],
                "max_new_tokens": 256,
                "temperature": 0.0,
                "thinking_budget": 0,
            }
        )

    return records


def build_bagel_reliability() -> list[dict[str, object]]:
    selected = [
        "official_meme.json",
        "official_octupusy.json",
        "official_women.json",
    ]

    records: list[dict[str, object]] = []

    for repeat_index in range(1, 11):
        for filename in selected:
            payload = json.loads((BAGEL_CASE_DIR / filename).read_text(encoding="utf-8"))
            image_path = ROOT / payload["local_path"]

            if not image_path.is_file():
                raise FileNotFoundError(f"BAGEL image missing: {image_path}")

            actual_hash = sha256(image_path)
            if actual_hash != payload["sha256"]:
                raise ValueError(
                    f"BAGEL image hash mismatch: {image_path}; "
                    f"expected={payload['sha256']}; actual={actual_hash}"
                )

            records.append(
                {
                    "case_id": f"{payload['case_id']}_repeat_{repeat_index}",
                    "scenario": "bagel_image_understanding_reliability",
                    "source_case_id": payload["case_id"],
                    "repeat_index": repeat_index,
                    "image_path": payload["local_path"],
                    "image_sha256": payload["sha256"],
                    "prompt": payload["prompt"],
                    "show_thinking": payload["show_thinking"],
                    "do_sample": payload["do_sample"],
                    "temperature": payload["temperature"],
                    "max_new_tokens": payload["max_new_tokens"],
                }
            )

    return records


def make_long_document(target_characters: int, label: str) -> str:
    sections: list[str] = []
    index = 1

    while len("\n".join(sections)) < target_characters:
        sections.append(
            f"""[Section {index:05d}: {label}]
Service policy record {index} describes order intake, payment verification,
warehouse handling, delivery exception triage, return processing, and customer
communication. The record requires agents to distinguish confirmed facts from
assumptions, preserve traceable case identifiers, and avoid inventing status.
Operational review item {index}: identify the responsible step, the evidence
required for escalation, and the next action for the customer.
"""
        )
        index += 1

    document = "\n".join(sections)
    return document[:target_characters]


def build_long_context() -> list[dict[str, object]]:
    specs = [
        ("long_context_medium", 60_000),
        ("long_context_large", 180_000),
    ]

    records: list[dict[str, object]] = []

    for case_id, target_characters in specs:
        filename = f"{case_id}.txt"
        output_path = OUTPUT_DIR / "long_context" / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        document = make_long_document(target_characters, case_id)
        output_path.write_text(document, encoding="utf-8")

        records.append(
            {
                "case_id": case_id,
                "scenario": "long_context_summary",
                "document_path": str(output_path.relative_to(ROOT)),
                "document_characters": len(document),
                "prompt_suffix": (
                    "\n\n请基于上述材料输出："
                    "1. 三项主要运营风险；2. 每项风险的证据；"
                    "3. 一个优先级排序后的处置建议。"
                    "不要添加材料中不存在的事实。"
                ),
                "max_new_tokens": 256,
                "temperature": 0.0,
                "thinking_budget": 0,
                "token_count_rule": (
                    "正式 GPU 实验前必须使用部署模型 tokenizer 记录实际 input_tokens；"
                    "不得将字符数直接写作 token 数。"
                ),
            }
        )

    return records


def main() -> None:
    customer_service = build_customer_service()
    codegen = build_codegen()
    bagel = build_bagel_reliability()
    long_context = build_long_context()

    write_jsonl(OUTPUT_DIR / "customer_service_short.jsonl", customer_service)
    write_jsonl(OUTPUT_DIR / "codegen_fixed.jsonl", codegen)
    write_jsonl(OUTPUT_DIR / "bagel_reliability_n30.jsonl", bagel)
    stale_bagel_manifest = OUTPUT_DIR / "bagel_reliability_n12.jsonl"
    if stale_bagel_manifest.exists():
        stale_bagel_manifest.unlink()
    write_jsonl(OUTPUT_DIR / "long_context_manifest.jsonl", long_context)

    summary = {
        "customer_service_short_count": len(customer_service),
        "codegen_fixed_count": len(codegen),
        "bagel_reliability_count": len(bagel),
        "bagel_note": (
            "n=30 是三个固定图文案例各重复十次，用于每个场景的稳定性、延迟和资源观测；"
            "不代表三十个独立图像覆盖场景。"
        ),
        "long_context_case_count": len(long_context),
        "long_context_note": (
            "文档按字符数固定；最终 input_tokens 必须在 GPU 环境用部署 tokenizer 实测。"
        ),
    }

    (OUTPUT_DIR / "manifest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
