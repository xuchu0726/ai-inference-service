# Week2 交付摘要：Seed-OSS-36B 推理服务性能优化与长上下文验证

## 1. 本周交付目标

本周目标是在 Week1 Seed-OSS-36B-Instruct 基础部署与 API 封装的基础上，进一步完成真实 GPU 环境下的性能分析、并发测试、长上下文验证、Prefix Cache 分析和图表化交付。

## 2. 核心环境

| 项目 | 配置 |
|---|---|
| 云平台 | RunPod |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理框架 | vLLM 0.11.2 |
| API 服务 | FastAPI + VLLMBackend |
| 精度 | BF16 |
| Tensor Parallel Size | 2 |
| 长上下文配置 | max_model_len=65536 |

## 3. 已完成实验

### 3.1 并发测试

完成 concurrency = 1 / 2 / 4 / 8 / 16 的 FastAPI + vLLM benchmark。

结论：

- QPS 随并发提升而提升；
- P50/P95 latency 小幅上升；
- error rate 保持 0；
- 体现 vLLM continuous batching 在吞吐提升与单请求延迟之间的 trade-off。

### 3.2 长上下文测试

完成 8K、16K、32K、56K、61.9K input tokens 级别的长上下文请求验证。

结论：

- 8K 到 56K 首次梯度测试中，latency 随 input tokens 增长而上升；
- output tokens/s 随 input tokens 增长而下降；
- 结果符合长上下文 prefill 成本上升预期；
- 61.9K near-limit 测试受 Prefix Cache 与 warm state 影响，已单独复测并解释。

### 3.3 Batch-Token 专项调优

完成 vLLM max_num_batched_tokens 专项调优实验，覆盖 4096、8192、16384、32768 四组配置，并进一步比较 short-output burst 与 long-output decode-heavy 两类 workload。

结论：

- short-output c8 burst 场景下，32768 profile 相比 8192 将 QPS 从 1.921 提升到 2.371，并将 P95 latency 从 7.350s 降至 3.415s；
- long-output c4 decode-heavy 场景下，8192 profile 更稳健，P95 latency 为 13.258s，而 32768 为 16.406s；
- max_num_batched_tokens 不存在全局最优配置，应根据 workload 类型选择 serving profile；
- 当前实验形成的是 profile 级别调优和 workload-aware batching policy foundation，不等同于完整生产级运行时动态批处理调度。

Evidence：

- docs/week2_batch_token_tuning_report.md
- results/week2_batch_tokens_workload_summary_20260525.csv
- figures/week2/batch_tokens/week2_batch_tokens_profile_decision.png

### 3.4 Prefix Cache 复测

针对 56K 与 61.9K latency 异常现象，进行了交替复测，并保存 vLLM metrics。

结论：

- 重复长文本请求下 prefix cache 命中显著；
- 缓存命中后的 latency 不能代表 cold prompt 长上下文性能；
- benchmark 必须区分 cold prompt、warm prompt、prefix-cache-hit prompt。

### 3.5 GSM8K 全量评测

完成 GSM8K test set 全量评测，通过 FastAPI `/generate` 接口调用 Seed-OSS-36B-Instruct。

| 指标 | 结果 |
|---|---:|
| 总样本数 | 1319 |
| API 成功样本数 | 1319 |
| API 失败样本数 | 0 |
| API error rate | 0.0 |
| 可解析答案样本数 | 1319 |
| 正确样本数 | 999 |
| Accuracy | 75.74% |
| Client latency P50 | 5.51s |
| Client latency P95 | 6.69s |
| Average tokens/s | 38.30 |
| Average output tokens | 206.77 |

该结果说明当前服务已经不只是 smoke test，而是具备真实任务级评测结果。GSM8K full benchmark 为 Seed-OSS-36B-Instruct 的数学推理能力、服务稳定性和端到端延迟提供了可量化基线。

Evidence：

- `results/week2_gsm8k_full_seed_oss_budget0_summary.csv`
- `artifacts/week2_seed_oss_gsm8k_codegen_dynamic_batch_evidence_20260518_042845.tar.gz`

### 3.6 代码生成 Mini Eval

完成 5 个 Python 代码生成小样本验证。

| 指标 | 结果 |
|---|---:|
| 总样本数 | 5 |
| API 成功样本数 | 5 |
| API 失败样本数 | 0 |
| 简单正确性检查 | 5 / 5 passed |
| Latency range | 0.505s – 1.627s |

测试任务覆盖简单 Python 函数生成，包括加法、奇偶判断、字符串反转、阶乘和单词计数。该测试不能替代 HumanEval 或 MBPP，但可以作为 Seed-OSS-36B-Instruct 代码生成能力的轻量验证。

Evidence：

- `results/week2_codegen_mini_seed_oss_budget0.csv`

## 4. 关键产物路径

| 内容 | 路径 |
|---|---|
| Week2 主性能报告 | docs/week2_performance_optimization_report.md |
| Batch-Token 调优专项报告 | docs/week2_batch_token_tuning_report.md |
| Workload-Aware Routing Policy 抽象说明 | docs/week2_routing_policy_abstraction.md |
| 长上下文汇总表 | docs/week2_context_gradient_summary.md |
| Prefix Cache 分析 | docs/week2_prefix_cache_investigation_summary.md |
| 64K RunPod 原始证据 | evidence/week2_64k_context/ |
| Pre-32K 原始证据 | evidence/week2_pre_32k/ |
| 原始压缩包 | artifacts/ |
| 性能图表 | figures/ |

## 5. 当前局限

当前 Week2 已完成 BF16 baseline、并发测试、64K 级别长上下文验证、Prefix Cache 分析、GSM8K full 评测和代码生成 mini eval。

仍未完成或需要后续补强的部分如下：

1. plain INT8 / AWQ / GPTQ 稳定 serving 尚未完成。本阶段已完成的是 W8A8 compressed-tensors 量化闭环；bitsandbytes INT8、INC INT8 和 compressed-tensors strict INT8 已记录失败边界，不能包装为最终成功路径。
2. FP8 KV cache 尚未完成。当前已完成 vLLM KV cache、PagedAttention、Prefix Cache 和长上下文边界行为分析，但尚未实测 KV cache 低比特量化。
3. 512K full-context 未完成实机验证。Week2 已完成 128K serving profile live boundary test，包括 conservative、near-limit 和 over-limit 三类请求。
4. 代码生成测试使用的是 Seed-OSS-36B-Instruct，不是专门的 Seed-Coder 模型。Seed-Coder 专项验证仍是后续任务。
5. Prometheus 配置、Grafana dashboard JSON 和一次 Grafana 实机导入/负载探测 evidence 已保存；后续仍可继续补充更完整的 dashboard、告警面板和长期监控截图。

## 6. 阶段结论

Week2 已经把项目从 API 可运行推进到真实大模型推理服务性能分析阶段。当前仓库具备可复现脚本、原始 evidence、CSV 结果、图表和正式性能报告，可作为后续 Week3 高可用架构、降级策略、多模态接入和 Week4 压测验收的基础。
