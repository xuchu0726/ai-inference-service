# Week2 GSM8K 与代码生成 Mini Eval 计划

## 1. 背景

Week2 任务书要求验证 Seed 模型的数学推理能力和代码生成能力。当前项目已完成 Seed-OSS-36B-Instruct 的 BF16 serving baseline、并发 benchmark、64K 长上下文验证和 Prefix Cache 分析。本文补充一个小规模、可复现的 mini eval 框架，用于在下一次 GPU 服务窗口中快速验证数学推理与代码生成能力。

## 2. 数据集

| Task | Path | Cases |
|---|---|---:|
| GSM8K mini | `data/eval/gsm8k_mini.jsonl` | 5 |
| Codegen mini | `data/eval/codegen_mini.jsonl` | 5 |

## 3. Runner

评测脚本路径：

```text
scripts/run_week2_eval_mini.py
```

该脚本调用 FastAPI `/generate` 接口，并保存以下字段：

| Field | Meaning |
|---|---|
| case_id | 测试样本 ID |
| task_type | gsm8k 或 codegen |
| status_code | API 状态码 |
| ok | 请求是否成功 |
| client_latency_seconds | 客户端端到端延迟 |
| server_latency_seconds | 服务端返回延迟 |
| backend | 推理后端 |
| model_name | 模型名称 |
| input_tokens | 输入 token 数 |
| output_tokens | 输出 token 数 |
| tokens_per_second | 输出 token/s |
| simple_correctness | 简单规则判断 |
| response_preview | 输出预览 |
| error | 错误信息 |

## 4. 运行方式

GSM8K mini eval:

```bash
python scripts/run_week2_eval_mini.py \
  --task-type gsm8k \
  --dataset data/eval/gsm8k_mini.jsonl \
  --output results/week2_gsm8k_mini_seed_oss.csv \
  --max-new-tokens 256 \
  --thinking-budget 512
```

Codegen mini eval:

```bash
python scripts/run_week2_eval_mini.py \
  --task-type codegen \
  --dataset data/eval/codegen_mini.jsonl \
  --output results/week2_codegen_mini_seed_oss.csv \
  --max-new-tokens 256 \
  --thinking-budget 512
```

## 5. 当前状态

当前阶段已完成 mini eval 数据集和 runner。由于本轮 RunPod GPU 服务已经停止，尚未生成 Seed-OSS-36B-Instruct 的真实 mini eval 结果。

下一次 GPU 窗口启动 FastAPI + vLLM 服务后，应优先运行该脚本并保存：

1. `results/week2_gsm8k_mini_seed_oss.csv`
2. `results/week2_codegen_mini_seed_oss.csv`
3. mini eval 运行日志；
4. 推理期间 nvidia-smi snapshot；
5. FastAPI/vLLM metrics snapshot；
6. 对错误样本进行人工分析。

## 6. 对 Week2 任务要求的回应

Week2 要求测试数学推理和代码生成能力。当前阶段完成了可复现评测框架，包括小样本数据、统一 runner 和结果 CSV schema。真实 Seed-OSS 推理结果将在下一次 GPU 服务窗口补充。
