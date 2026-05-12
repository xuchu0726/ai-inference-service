# 第 2 周性能优化报告：Seed-OSS-36B 推理服务性能分析与模型特性验证

## 1. 本周目标

第 2 周目标是在第 1 周已完成 Seed-OSS-36B-Instruct 基础部署、FastAPI 封装、vLLM 接入、Thinking Budget 参数链路和 Prometheus 基础监控的基础上，进一步推进推理服务的性能分析与优化验证。

本周重点从“服务跑通”升级为“性能可观测、瓶颈可分析、优化有数据支撑”。

核心工作包括：

1. 使用 Prometheus + Grafana 分析推理服务指标、GPU 使用情况和内存瓶颈；
2. 扩展并发性能测试，统计 QPS、P50/P95 latency、tokens/s 和 error_rate；
3. 做上下文长度梯度测试，分析 context length 对显存、KV Cache、延迟和吞吐的影响；
4. 评估 Seed-OSS-36B 量化优化路径，形成 BF16 baseline 与可落地量化方案的对比；
5. 结合 GQA 与 KV Cache 机制解释长上下文和高并发下的性能变化；
6. 补充 GSM8K 数学推理与代码生成场景验证；
7. 完成 FAQ、API 错误码和边界情况说明，提升服务可维护性。

---

## 2. Week1 基线回顾

第 1 周已完成以下基线能力：

| 项目 | 当前状态 |
|---|---|
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理引擎 | vLLM 0.11.2 |
| API 层 | FastAPI |
| 后端适配 | VLLMBackend |
| GPU | 2×NVIDIA A100-SXM4-80GB |
| dtype | bfloat16 |
| Tensor Parallel | TP=2 |
| max_model_len | 4096 |
| max_num_batched_tokens | 8192 |
| FastAPI metrics | 已接入 |
| vLLM metrics | 已验证 |
| Thinking Budget | 512 / 1024 已验证 |
| 初步并发测试 | concurrency=2 / 4 |
| 稳定运行显存 | 约 75.8GB / 80GB per GPU |

Week1 结论：

1. Seed-OSS-36B-Instruct 已完成基础服务化部署；
2. FastAPI + VLLMBackend + vLLM Server 架构可用；
3. 当前 4K context 下 BF16 TP=2 配置可运行；
4. 显存压力已经较高，后续长上下文和更高并发必须逐步测试；
5. 512K full-context 不应直接硬冲，需要先做上下文长度梯度测试和资源边界分析。

---

## 3. Week2 交付范围

本周交付分为 7 类。

### 3.1 监控与可观测性

目标：

1. 配置 Prometheus scrape；
2. 搭建或记录 Grafana dashboard；
3. 展示 FastAPI、vLLM 和 GPU 相关指标；
4. 为后续性能瓶颈分析提供数据来源。

关注指标：

| 类型 | 指标 |
|---|---|
| FastAPI | request count, request latency, status code |
| vLLM | running requests, waiting requests, KV cache usage, prefix cache |
| GPU | memory used, utilization |
| Benchmark | QPS, P50, P95, tokens/s, error_rate |

---

### 3.2 并发 / Batch 性能测试

目标：

测试不同并发度下服务吞吐、尾延迟和稳定性变化。

计划测试矩阵：

| concurrency | max_new_tokens | thinking_budget | 说明 |
|---:|---:|---:|---|
| 1 | 128 | 512 | 单请求基线 |
| 2 | 128 | 512 | 小并发 |
| 4 | 128 | 512 | Week1 已验证，Week2 复测 |
| 8 | 128 | 512 | 中等并发 |
| 16 | 128 | 512 | 高阶尝试 |

记录指标：

1. total_requests；
2. successful_requests；
3. failed_requests；
4. error_rate；
5. QPS；
6. client_latency_avg；
7. client_latency_p50；
8. client_latency_p95；
9. tokens_per_second_avg；
10. GPU memory；
11. vLLM running/waiting requests；
12. KV cache usage。

预期图表：

1. QPS vs concurrency；
2. P95 latency vs concurrency；
3. tokens/s vs concurrency；
4. error_rate vs concurrency；
5. GPU memory vs concurrency。

---

### 3.3 上下文长度梯度测试

目标：

回应 Week1 中 max_model_len=4096 与 Seed-OSS 原生 512K 能力差距较大的问题，用分阶段实验分析长上下文下的显存、延迟和稳定性边界。

计划测试矩阵：

| context length | 目标 |
|---:|---|
| 4K | Week1 基线复测 |
| 8K | 低风险扩展 |
| 16K | 中等长度扩展 |
| 32K | 高阶尝试 |
| 64K | 资源允许时尝试 |

记录指标：

1. input_tokens；
2. output_tokens；
3. max_model_len；
4. latency；
5. P50 / P95；
6. tokens/s；
7. GPU memory；
8. KV cache usage；
9. error_rate；
10. 是否 OOM；
11. 是否 timeout。

说明：

512K full-context 是 Seed-OSS 的目标能力，但直接进行 512K 测试会带来显著显存、prefill latency 和 OOM 风险。本周优先采用 4K/8K/16K/32K 梯度测试，用数据推导资源边界和后续 512K 专项测试所需条件。

---

### 3.4 量化优化可行性与对比

任务书要求：

    INT8 量化，对比 FP32 精度下的速度与显存占用。

当前资源边界：

Week1 实测中，Seed-OSS-36B-Instruct 在 BF16、TP=2、max_model_len=4096 下，2×A100 80GB 稳定运行时每张卡显存约 75.8GB/80GB。FP32 权重显存理论上约为 BF16 的 2 倍，因此 FP32 serving baseline 在当前资源下可能需要更多 GPU 或调整实验方案。

本周实际方案：

1. 以 BF16 作为实际 serving baseline；
2. 调研 vLLM 对 Seed-OSS-36B 的 INT8 / FP8 / AWQ / GPTQ 支持情况；
3. 若可落地，则运行量化版本并对比显存、P95、tokens/s；
4. 若不可落地，则保留兼容性分析、失败日志和替代方案；
5. 输出量化可行性对比表。

量化对比表模板：

| 方案 | 是否跑通 | GPU memory | P95 latency | tokens/s | 质量观察 | 备注 |
|---|---|---:|---:|---:|---|---|
| BF16 baseline | 是 | 待填 | 待填 | 待填 | 待填 | Week1/Week2 基线 |
| INT8 | 待验证 | 待填 | 待填 | 待填 | 待填 | 依赖 vLLM/权重兼容 |
| FP8/AWQ/GPTQ | 待验证 | 待填 | 待填 | 待填 | 待填 | 可落地替代方案 |

---

### 3.5 KV Cache 与 GQA 分析

目标：

结合 Week2 的并发和上下文长度实验，解释 GQA 和 KV Cache 如何影响 Seed-OSS-36B 的推理性能。

重点分析：

1. GQA 如何减少 key/value head 数量；
2. GQA 如何降低 KV Cache 显存压力；
3. 上下文长度增长时 KV Cache usage 如何变化；
4. concurrency 增加时 running/waiting requests 如何变化；
5. P95 latency 上升是否来自排队、prefill、decode 或显存压力。

---

### 3.6 GSM8K 数学推理验证

目标：

验证 Seed-OSS-36B 在数学推理任务上的基本能力，并记录推理服务指标。

计划：

1. 选取 GSM8K 小样本；
2. 记录 prompt、response、latency、output_tokens；
3. 人工判断是否正确；
4. 汇总 accuracy、平均 latency 和错误类型。

结果表模板：

| case_id | correct | latency | output_tokens | thinking_budget | 备注 |
|---:|---|---:|---:|---:|---|
| 1 | 待填 | 待填 | 待填 | 512 | 待填 |

---

### 3.7 代码生成验证

目标：

验证 Seed 模型在代码生成场景中的基础表现，为后续 Seed-Coder 或代码助手场景做准备。

计划：

1. 准备 5-10 个代码生成 prompt；
2. 覆盖 Python 函数、数据处理、API 调用、错误修复等场景；
3. 记录 latency、output_tokens、是否可运行；
4. 总结常见错误类型。

结果表模板：

| case_id | task_type | runnable | latency | output_tokens | 备注 |
|---:|---|---|---:|---:|---|
| 1 | Python function | 待填 | 待填 | 待填 | 待填 |

---

## 4. Week2 新增文档

为回应 Week1 反馈，本周新增：

1. `docs/troubleshooting_faq.md`
2. `docs/api_error_codes.md`

这两份文档用于提升服务的可维护性和可排查性。

---

## 5. 实验结果索引

本节等待 Week2 实验执行后填入。

### 5.1 并发 benchmark

计划文件：

    results/week2_concurrency_benchmark.csv
    results/week2_concurrency_summary.csv

### 5.2 上下文长度 benchmark

计划文件：

    results/week2_context_length_benchmark.csv
    results/week2_context_length_summary.csv

### 5.3 量化可行性

计划文件：

    results/week2_quantization_comparison.csv
    docs/week2_quantization_notes.md

### 5.4 GSM8K

计划文件：

    results/week2_gsm8k_eval.csv

### 5.5 代码生成

计划文件：

    results/week2_code_generation_eval.csv

### 5.6 图表

计划文件：

    figures/week2_qps_vs_concurrency.png
    figures/week2_p95_vs_concurrency.png
    figures/week2_tokens_per_second_vs_concurrency.png
    figures/week2_gpu_memory_vs_context.png
    figures/week2_kv_cache_usage_vs_context.png

---

## 6. 当前风险与处理策略

| 风险 | 影响 | 处理策略 |
|---|---|---|
| FP32 baseline 显存过高 | 无法按字面完成 FP32 vs INT8 | 使用 BF16 serving baseline，并说明 FP32 资源需求 |
| INT8 路径不兼容 | 量化实验无法直接跑通 | 记录兼容性和失败日志，改用可支持方案 |
| 32K/64K OOM | 长上下文实验失败 | 保留 OOM 边界，降低 context length |
| 高并发 timeout | benchmark 失败率上升 | 保留失败样本，降低 concurrency 或增加 timeout |
| Grafana 配置耗时 | 影响主实验 | 先完成 Prometheus + dashboard notes，再补 JSON |
| GPU 成本过高 | 试错成本增加 | 先本地准备脚本和报告框架，再集中跑 GPU |

---

## 7. 阶段结论模板

本节将在 Week2 实验完成后填写。

预期总结方向：

1. Seed-OSS-36B-Instruct 在不同并发下的 QPS、P95 和 tokens/s 变化；
2. 上下文长度增长对显存、KV Cache 和尾延迟的影响；
3. BF16 baseline 与可落地量化方案的差异；
4. Prometheus/Grafana 对性能瓶颈分析的作用；
5. GSM8K 和代码生成验证结果；
6. 当前资源下无法直接完成 FP32/512K 的原因与后续资源需求评估；
7. 下一步向高可用、多模态和压测验收推进的计划。
