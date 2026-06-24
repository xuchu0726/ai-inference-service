# Week2 交付完成度与证据索引

> **当前口径（2026-06-24）**：本矩阵主体保留原始交付阶段状态。若下文与当前主报告冲突，以 `docs/week2_performance_optimization_report.md` 和 `docs/week2_hardening_response_summary.md` 为准。当前状态：512K / FP8 KV 单请求边界验证已完成；AWQ-Marlin 独立 serving-stack 与 full GSM8K 已完成；BnB INT8 runtime 已完成 GSM8K `@256` 全量 1319 题评测及 348 个 cap-hit 样本 `@768` 补测；compressed-tensors strict INT8 stable vLLM serving 与 GPTQ 未完成；代码生成已扩展至 50 个轻量任务，26/50 通过；FP32/W8A8 为实际 deployment-stack 对比，不是全参数严格单变量消融。


## 1. 总体结论

本文件用于将 Week2 性能优化与 Seed 模型特性验证要求，对应到当前仓库中已经完成的实验、代码、日志、图表和文档证据。

当前已经形成闭环的内容包括：

- Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 环境下的 BF16 与 FP32 serving baseline；
- Seed-OSS-36B-Instruct 的 W8A8 compressed-tensors 离线量化与 vLLM serving；
- FP32 batch profile 与 W8A8 batch profile 的同参数并发对比；
- QPS、P95 latency、output tokens/s 对比图；
- `max_num_batched_tokens` 多组配置调优；
- workload-aware serving profile 与 routing abstraction；
- Prometheus、Grafana、vLLM metrics 和 `nvidia-smi` 监控证据；
- KV cache、prefix cache 和 PagedAttention 相关分析；
- GSM8K full benchmark；
- Seed-OSS-36B-Instruct 代码生成 mini eval；
- 64K 长上下文梯度测试、128K serving profile 边界验证和 512K 可行性分析。

当前阶段边界包括：

- 最终稳定量化路径是 W8A8 compressed-tensors，而不是 plain INT8、AWQ 或 GPTQ 稳定 serving；
- `nvidia-smi` 运行时总显存没有按 30% 以上同比下降，因为 vLLM 会把释放出的模型权重显存重新用于 KV cache；
- 代码生成验证使用 Seed-OSS-36B-Instruct 完成，Seed-Coder 专项模型部署与评测尚未纳入本阶段交付；
- 当前已有 64K live context evidence、128K serving profile live boundary test 和 512K 可行性分析，512K full-context 实机验证尚未完成；
- FP8 KV cache / KV cache quantization 尚未完成实机验证。

## 2. 文档入口

| 目的 | 文档 |
|---|---|
| Week2 交付摘要 | [`docs/week2_delivery_summary.md`](../docs/week2_delivery_summary.md) |
| Week2 主性能报告 | [`docs/week2_performance_optimization_report.md`](../docs/week2_performance_optimization_report.md) |
| Batch-token 调优专项报告 | [`docs/week2_batch_token_tuning_report.md`](../docs/week2_batch_token_tuning_report.md) |
| 量化实验报告 | [`docs/week2_quantization_feasibility_report.md`](../docs/week2_quantization_feasibility_report.md) |
| 可观测性报告 | [`docs/week2_observability_report.md`](../docs/week2_observability_report.md) |
| GSM8K 与代码生成评测报告 | [`docs/week2_eval_mini_report.md`](../docs/week2_eval_mini_report.md) |
| 128K 长上下文边界复盘 | [`docs/week2/seed_oss_128k_context_boundary_review.md`](../docs/week2/seed_oss_128k_context_boundary_review.md) |
| 512K 可行性分析 | [`docs/week2_512k_feasibility_and_resource_analysis.md`](../docs/week2_512k_feasibility_and_resource_analysis.md) |
| 故障排查手册 | [`docs/troubleshooting_faq.md`](../docs/troubleshooting_faq.md) |
| API 错误码与边界说明 | [`docs/api_error_codes.md`](../docs/api_error_codes.md) |

## 3. Week2 交付项逐项映射

| 交付项 | 当前证据 | 完成状态 | 客观说明 |
|---|---|---|---|
| 使用 Prometheus + Grafana 分析 GPU 利用率、内存瓶颈 | [`deployment/monitoring/prometheus_week2.yml`](../deployment/monitoring/prometheus_week2.yml)、[`deployment/monitoring/grafana_week2_seed_oss_dashboard.json`](../deployment/monitoring/grafana_week2_seed_oss_dashboard.json)、[`figures/week2/observability/week2_grafana_seed_oss_live_load_probe.png`](../figures/week2/observability/week2_grafana_seed_oss_live_load_probe.png)、vLLM metrics、`nvidia-smi` snapshot/sampling | 已完成 | 已保存 Prometheus 配置、Grafana dashboard JSON、Grafana live load probe、vLLM metrics 和 GPU 侧证据。GPU 利用率与显存瓶颈主要通过 Grafana evidence 和 `nvidia-smi` 记录支撑。 |
| 实施 Seed-OSS 低比特量化 | W8A8 compressed-tensors offline quantization、vLLM serving、smoke test、batch-profile benchmark | 已完成 / 有边界 | 已完成稳定可复现的 W8A8 compressed-tensors 量化 serving。plain INT8、AWQ、GPTQ 路线已做兼容性探测，但未形成稳定 serving 闭环。 |
| 对比 FP32 精度下速度与显存占用 | FP32 baseline、W8A8 batch profile、对比 CSV 和图表 | 已完成 | 已完成同 serving 参数下 FP32 vs W8A8 对比。 |
| 量化前后性能对比表 | [`results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`](../results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv) | 已完成 | 对比表覆盖 concurrency=1/2/4/8/16 下的 QPS、P95 latency、output tokens/s 和提升比例。 |
| 显存降低 ≥30% | FP32 vs W8A8 model loading memory 对比 | 按 model loading memory 口径完成 | model loading memory 从约 67.59 GiB 降至约 17.71 GiB，下降约 73.8%。运行时总显存不作为该指标口径，因为 vLLM 会将释放出的权重显存用于扩展 KV cache。 |
| 速度提升 ≥20% | FP32 vs W8A8 batch-profile improvement CSV 和图表 | 已完成 | W8A8 在 concurrency=1/2/4/8/16 下 QPS 与 output tokens/s 提升约 31.4% 到 126.1%。 |
| 动态 Batch 调度 | `max_num_batched_tokens` sweep、batch-token tuning 图表、workload-aware profile、[`app/routing.py`](../app/routing.py) | 已完成 | 当前实现是 profile-level batch-token tuning 与 workload-aware routing abstraction。由于 `max_num_batched_tokens` 是 vLLM 启动参数，本阶段采用多 serving profile + routing abstraction 的工程路线。 |
| Batch Size / Batch-token 测试图表 | [`figures/week2/batch_tokens/`](../figures/week2/batch_tokens) | 已完成 | 覆盖 4096、8192、16384、32768 等 batch-token 配置，并区分 short-output burst 与 long-output decode-heavy workload。 |
| KV 缓存优化 | vLLM KV cache、prefix cache metrics、PagedAttention、context length experiments | 已完成 | 本阶段基于 vLLM 的 PagedAttention、KV cache 和 prefix cache 机制完成启用、观测和分析，没有改写底层 KV cache kernel。 |
| GQA 如何降低计算复杂度 | [`docs/week2_performance_optimization_report.md`](../docs/week2_performance_optimization_report.md)、相关 Week2 文档 | 已完成 | 通过 GQA 减少 key/value head 数量、降低 KV cache 显存压力，并结合长上下文与并发实验解释性能变化。 |
| QPS、延迟、P95 优化图表 | concurrency 图、batch-token 图、FP32 vs W8A8 图 | 已完成 | 图表覆盖吞吐、尾延迟、tokens/s、error rate 和量化前后对比。 |
| GSM8K 数学推理 | GSM8K full benchmark、summary、日志、metrics | 已完成 | 已完成 1319 条 GSM8K test set 的完整评测，API error rate 为 0，accuracy 为 75.74%。 |
| 代码生成验证 | Seed-OSS-36B-Instruct codegen mini eval | 已完成 / 有边界 | 已完成 5 个 Python 代码生成 mini eval，全部 API 成功并通过简单正确性检查。Seed-Coder 专项模型评测未纳入本阶段交付。 |
| 128K long-context boundary test | 128K conservative / near-limit / over-limit CSV、vLLM launch log、ready check、boundary review | 已完成 | 已完成 128K serving profile live boundary test。512K full-context 实机验证尚未完成。 |
| FP8 KV cache / KV cache quantization | 当前无实机 evidence | 未完成 | 该方向与长上下文 KV cache capacity 直接相关，保留为后续优化方向。 |

## 4. 当前阶段范围与后续方向

当前阶段已经覆盖 Week2 性能优化与模型特性验证的主体内容，包括可观测性、并发测试、batch-token 调优、长上下文、量化对比、KV cache/GQA 分析、GSM8K 和代码生成验证。

后续仍需推进的方向包括：

1. 512K full-context 实机验证或更高资源配置下的分阶段边界测试；
2. FP8 KV cache / KV cache quantization 实机验证；
3. Seed-Coder 专项模型部署与代码生成 benchmark；
4. 多 serving profile 的真实 gateway routing；
5. 更完整的 Grafana dashboard、告警规则和长时间 Prometheus TSDB 留存；
6. Week3 高可用、降级策略、多实例服务治理与 Week4 压测验收。
