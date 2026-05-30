# Week2 模型能力评测报告：GSM8K Full Benchmark 与代码生成 Mini Eval

## 1. 文档目的

Week2 任务要求验证 Seed 模型在数学推理和代码生成任务上的能力。本文记录 Seed-OSS-36B-Instruct 在当前 FastAPI + VLLMBackend + vLLM serving 架构下完成的 GSM8K 全量评测和代码生成 mini eval。

本评测的目的不是简单验证模型能否返回文本，而是同时记录：

1. 任务正确率；
2. API 成功率；
3. 端到端 latency；
4. tokens/s；
5. output tokens；
6. 结果文件和 evidence 路径。

---

## 2. 服务配置

| 项目 | 配置 |
|---|---|
| 云平台 | RunPod |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理引擎 | vLLM 0.11.2 |
| API 层 | FastAPI + VLLMBackend |
| 精度 | BF16 |
| Tensor Parallel Size | 2 |
| max_model_len | 65536 |
| vLLM port | 8002 |
| FastAPI port | 8000 |

---

## 3. GSM8K Full Benchmark

### 3.1 实验配置

| 项目 | 配置 |
|---|---|
| Dataset | GSM8K test set |
| Total cases | 1319 |
| Endpoint | FastAPI `/generate` |
| max_new_tokens | 256 |
| temperature | 0.0 |
| thinking_budget | 0 |
| timeout_seconds | 1800 |
| Resume support | enabled |

运行命令：

~~~bash
python scripts/run_gsm8k_full_benchmark.py \
  --url http://127.0.0.1:8000/generate \
  --dataset data/eval/gsm8k_test.jsonl \
  --dataset-url https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl \
  --download-if-missing \
  --output results/week2_gsm8k_full_seed_oss_budget0.csv \
  --summary-output results/week2_gsm8k_full_seed_oss_budget0_summary.csv \
  --max-new-tokens 256 \
  --temperature 0.0 \
  --thinking-budget 0 \
  --timeout-seconds 1800 \
  --resume
~~~

### 3.2 实验结果

| 指标 | 结果 |
|---|---:|
| Total cases | 1319 |
| Successful API cases | 1319 |
| Failed API cases | 0 |
| API error rate | 0.0 |
| Parseable answer cases | 1319 |
| Correct cases | 999 |
| Accuracy | 75.74% |
| Client latency average | 5.40s |
| Client latency P50 | 5.51s |
| Client latency P95 | 6.69s |
| Server latency average | 5.40s |
| Server latency P50 | 5.51s |
| Server latency P95 | 6.69s |
| Average tokens/s | 38.30 |
| Average output tokens | 206.77 |

### 3.3 结果解释

GSM8K full benchmark 全部 1319 个样本均通过 API 成功返回，API error rate 为 0。这说明当前 FastAPI + VLLMBackend + vLLM Server 链路在长时间顺序推理任务中保持稳定。

最终正确样本数为 999，accuracy 为 75.74%。该结果提供了一个真实任务级数学推理基线，价值高于单条 smoke test 或少量人工 prompt 验证。

本次正式全量评测使用 `thinking_budget=0`。原因是前置 diagnostic run 显示，在当前评测脚本和答案抽取逻辑下，`thinking_budget=512` 会产生更长的思考输出，但不一定提高最终可解析答案的准确率，并且显著增加 latency。因此，最终 full benchmark 选择更稳定、更适合自动评测的 `thinking_budget=0` 配置。

该现象说明：推理深度参数并不是越大越好。在线推理系统需要同时控制输出格式、答案抽取、latency 和任务正确率。

---

## 4. Code Generation Mini Eval

### 4.1 实验配置

| 项目 | 配置 |
|---|---|
| Dataset | [`data/eval/codegen_mini.jsonl`](../data/eval/codegen_mini.jsonl) |
| Cases | 5 |
| Endpoint | FastAPI `/generate` |
| max_new_tokens | 256 |
| temperature | 0.0 |
| thinking_budget | 0 |
| timeout_seconds | 1800 |

运行命令：

~~~bash
python scripts/run_week2_eval_mini.py \
  --url http://127.0.0.1:8000/generate \
  --task-type codegen \
  --dataset data/eval/codegen_mini.jsonl \
  --output results/week2_codegen_mini_seed_oss_budget0.csv \
  --max-new-tokens 256 \
  --temperature 0.0 \
  --thinking-budget 0 \
  --timeout-seconds 1800
~~~

### 4.2 实验结果

| Case | 任务 | 状态 | Latency |
|---|---|---|---:|
| codegen_001 | Python add function | pass | 0.540s |
| codegen_002 | even number check | pass | 0.614s |
| codegen_003 | reverse string | pass | 0.530s |
| codegen_004 | factorial function | pass | 1.627s |
| codegen_005 | word count function | pass | 0.505s |

汇总结果：

| 指标 | 结果 |
|---|---:|
| Total cases | 5 |
| Successful API cases | 5 |
| Failed API cases | 0 |
| Simple correctness | 5 / 5 passed |
| Latency range | 0.505s – 1.627s |

### 4.3 结果解释

代码生成 mini eval 覆盖了 5 个简单 Python 函数生成任务。模型生成结果均通过简单正确性检查，说明 Seed-OSS-36B-Instruct 在基础代码生成场景下具备可用输出能力。

需要注意的是，该测试不能替代 HumanEval、MBPP 或 Seed-Coder 专项 benchmark。它的定位是 Week2 阶段的轻量功能验证，用于证明当前推理服务不仅能处理自然语言问答，也可以通过同一 `/generate` API 支持基础代码生成场景。

---

## 5. Evidence 路径

| Evidence | Path |
|---|---|
| GSM8K full summary | [`results/week2_gsm8k_full_seed_oss_budget0_summary.csv`](../results/week2_gsm8k_full_seed_oss_budget0_summary.csv) |
| Codegen mini result | [`results/week2_codegen_mini_seed_oss_budget0.csv`](../results/week2_codegen_mini_seed_oss_budget0.csv) |
| GPU snapshot after GSM8K | [`logs/week2_nvidia_smi_after_gsm8k_full_budget0.txt`](../logs/week2_nvidia_smi_after_gsm8k_full_budget0.txt) |
| GPU snapshot after codegen | [`logs/week2_nvidia_smi_after_codegen_mini_budget0.txt`](../logs/week2_nvidia_smi_after_codegen_mini_budget0.txt) |
| vLLM metrics after GSM8K | [`results/week2_vllm_metrics_after_gsm8k_full_budget0.txt`](../results/week2_vllm_metrics_after_gsm8k_full_budget0.txt) |
| FastAPI metrics after GSM8K | [`results/week2_fastapi_metrics_after_gsm8k_full_budget0.txt`](../results/week2_fastapi_metrics_after_gsm8k_full_budget0.txt) |
| vLLM metrics after codegen | [`results/week2_vllm_metrics_after_codegen_mini_budget0.txt`](../results/week2_vllm_metrics_after_codegen_mini_budget0.txt) |
| FastAPI metrics after codegen | [`results/week2_fastapi_metrics_after_codegen_mini_budget0.txt`](../results/week2_fastapi_metrics_after_codegen_mini_budget0.txt) |
| Evidence package | [`artifacts/week2_seed_oss_gsm8k_codegen_dynamic_batch_evidence_20260518_042845.tar.gz`](../artifacts/week2_seed_oss_gsm8k_codegen_dynamic_batch_evidence_20260518_042845.tar.gz) |

---

## 6. 当前局限

1. Codegen mini eval 只有 5 个样本，不能代表完整代码生成 benchmark。
2. 本轮代码生成测试使用 Seed-OSS-36B-Instruct，而不是专门的 Seed-Coder 模型。
3. GSM8K accuracy 依赖答案抽取规则。部分错误样本可能包含中间推理正确但最终答案格式不符合抽取规则的情况。
4. 当前 GSM8K full benchmark 是顺序评测，不是高并发质量评测。
5. 当前结果可作为 BF16 serving baseline，后续若进行 INT8/AWQ/GPTQ/FP8 KV Cache 优化，需要重新跑 GSM8K/codegen 质量回归。

---

## 7. 阶段结论

Week2 已完成 Seed-OSS-36B-Instruct 在当前推理服务架构下的数学推理和代码生成验证。

GSM8K full benchmark 完成 1319 个样本，API error rate 为 0，accuracy 为 75.74%，client latency P50 为 5.51s，P95 为 6.69s。Codegen mini eval 完成 5 个 Python 函数生成任务，全部通过简单正确性检查。

这些结果为项目提供了真实任务级能力证据，也为后续量化优化、低预算推理降级、Seed-Coder 专项验证和业务场景测试提供了质量基线。
