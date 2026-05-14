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

### 3.3 Prefix Cache 复测

针对 56K 与 61.9K latency 异常现象，进行了交替复测，并保存 vLLM metrics。

结论：

- 重复长文本请求下 prefix cache 命中显著；
- 缓存命中后的 latency 不能代表 cold prompt 长上下文性能；
- benchmark 必须区分 cold prompt、warm prompt、prefix-cache-hit prompt。

## 4. 关键产物路径

| 内容 | 路径 |
|---|---|
| Week2 主性能报告 | docs/week2_performance_optimization_report.md |
| 长上下文汇总表 | docs/week2_context_gradient_summary.md |
| Prefix Cache 分析 | docs/week2_prefix_cache_investigation_summary.md |
| 64K RunPod 原始证据 | evidence/week2_64k_context/ |
| Pre-32K 原始证据 | evidence/week2_pre_32k/ |
| 原始压缩包 | artifacts/ |
| 性能图表 | figures/ |

## 5. 当前局限

当前实验已完成 BF16 baseline、并发测试、64K 级别长上下文验证和 Prefix Cache 分析。INT8 量化、FP32 对比、512K full-context、GSM8K 全量评测、Seed-Coder 专项验证仍需要更多 GPU 资源和独立实验窗口支持。

## 6. 阶段结论

Week2 已经把项目从 API 可运行推进到真实大模型推理服务性能分析阶段。当前仓库具备可复现脚本、原始 evidence、CSV 结果、图表和正式性能报告，可作为后续 Week3 高可用架构、降级策略、多模态接入和 Week4 压测验收的基础。
