# Week2 交付完成度与证据索引

## 1. 总体结论

本文件用于将 Week2 性能优化与 Seed 模型特性验证要求，对应到当前仓库中已经完成的真实实验、代码、日志、图表和文档证据。

当前已经形成闭环的内容包括：

- Seed-OSS-36B-Instruct 在 2×A100 环境下的 FP32 serving baseline；
- Seed-OSS-36B-Instruct 的 W8A8 compressed-tensors 离线量化与 vLLM serving；
- FP32 batch profile 与 W8A8 batch profile 的同参数并发对比；
- QPS、P95 latency、output tokens/s 对比图；
- `max_num_batched_tokens` 多组配置调优；
- workload-aware serving profile / routing abstraction；
- Prometheus / Grafana / vLLM metrics / nvidia-smi 监控证据；
- KV cache / prefix cache / PagedAttention 相关分析；
- GSM8K 数学推理评测；
- Seed-OSS 代码生成 mini eval；
- 64K 长上下文边界测试与 512K 可行性分析。

当前仍然不能夸大的边界包括：

- 最终稳定量化路径是 W8A8 compressed-tensors，不是 plain INT8 / AWQ / GPTQ；
- `nvidia-smi` 运行时总显存没有按 30% 以上下降，因为 vLLM 会把释放出的模型权重显存重新用于 KV cache；
- 已完成的是 Seed-OSS 代码生成 mini eval，不是 Seed-Coder 专项模型部署与评测；
- 当前已有 64K live context evidence、128K serving profile live boundary test 和 512K 可行性分析；
- 当前没有完成 FP8 KV cache / KV cache quantization 实机启动实验。

## 2. 推荐阅读顺序

| 阅读目的 | 推荐文档 |
|---|---|
| 快速了解 Week2 完成内容 | `docs/week2_delivery_summary.md` |
| 核对交付项、完成度和边界 | `docs/week2_requirement_compliance_matrix.md` |
| 查看完整性能分析 | `docs/week2_performance_optimization_report.md` |
| 查看 batch-token 调优实验 | `docs/week2_batch_token_tuning_report.md` |
| 查看量化实验与 FP32/W8A8 对比 | `docs/week2_quantization_feasibility_report.md` |
| 查看监控、Prometheus、Grafana 和 GPU 证据 | `docs/week2_observability_report.md` |
| 查看 GSM8K 与代码生成评测 | `docs/week2_eval_mini_report.md` |
| 查看 128K 长上下文边界实验 | `docs/week2/seed_oss_128k_context_boundary_review.md` |

## 3. Week2 交付项逐项映射

| 交付项 | 当前证据 | 完成状态 | 说明 |
|---|---|---|---|
| 使用 Prometheus + Grafana 分析 GPU 利用率、内存瓶颈 | `deployment/monitoring/prometheus_week2.yml`、`deployment/monitoring/grafana_week2_seed_oss_dashboard.json`、`figures/week2_grafana_seed_oss_live_load_probe.png`、Prometheus targets JSON、vLLM metrics、nvidia-smi 日志 | 已完成 | GPU 显存、请求队列、KV cache、吞吐和延迟都有证据。GPU 利用率主要通过 Grafana 证据和 nvidia-smi snapshot 支撑。 |
| 实施 Seed-OSS INT8 量化 | bitsandbytes INT8、INC INT8、compressed-tensors strict INT8 尝试；W8A8 compressed-tensors 成功 serving | 部分完成 / 有边界 | strict INT8/AWQ/GPTQ 没有形成最终稳定 serving。最终闭环的是 W8A8 compressed-tensors，属于 8-bit 权重量化路径。 |
| 对比 FP32 精度下速度与显存占用 | FP32 baseline、FP32 batch profile、W8A8 batch profile、对比 CSV 和图表 | 已完成 | 已完成同 serving 参数下 FP32 vs W8A8 对比。 |
| 显存降低 ≥30% | FP32 vs W8A8 model loading memory 对比 | 部分完成 | model loading memory 从约 67.59 GiB 降至约 17.71 GiB，降低约 73.8%。但 runtime `nvidia-smi` 总显存没有同比下降，因为 vLLM 扩大了 KV cache。报告中必须明确这一点。 |
| 速度提升 ≥20% | FP32 vs W8A8 batch profile improvement CSV 和图表 | 已完成 | W8A8 在 concurrency=1/2/4/8/16 下 QPS 与 output tokens/s 提升约 31.4% 到 126.1%。 |
| 动态 Batch 调度 | `max_num_batched_tokens` sweep、batch-token tuning 图表、workload-aware profile、`app/routing.py` | 已完成 | 实现方式是多 serving profile + routing abstraction，不是运行时热修改单个 vLLM engine 参数。 |
| KV 缓存优化 | vLLM KV cache、prefix cache metrics、PagedAttention、context length experiments | 已完成 | 项目没有重写底层 KV cache，而是基于 vLLM 的 PagedAttention/KV cache 机制启用并分析缓存行为。 |
| GSM8K 数学推理 | full GSM8K benchmark、summary、日志、metrics | 已完成 | 已完成完整 GSM8K 评测闭环。 |
| 代码生成，结合 Seed-Coder | Seed-OSS codegen mini eval | 部分完成 | 已验证代码生成场景，但没有完成 Seed-Coder 专项模型部署与评测。不能写“已完成 Seed-Coder eval”。 |
| 性能优化报告 | `docs/week2_performance_optimization_report.md` 等 Week2 文档 | 已完成 | 主报告已整合并发测试、长上下文、128K 边界验证、FP32 vs W8A8 量化对比、GSM8K、代码生成和未完成边界。 |
| 量化前后性能对比表 | `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv` | 已完成 | 对比表已形成，但表述必须写成 FP32 vs W8A8，而不是 FP32 vs plain INT8。 |
| Batch Size 测试图表 | `figures/week2/batch_tokens/` 下多张 QPS/P95/latency 图 | 已完成 | 已覆盖 4096/8192/16384/32768 等 batch-token 配置。 |
| GQA 如何降低计算复杂度 | Week2 报告和相关文档 | 已完成 | 已结合 GQA、KV cache、长上下文和并发 serving 场景解释其对显存压力和推理复杂度的影响。 |
| QPS、延迟、P95 优化图表 | batch-token 图、concurrency 图、FP32 vs W8A8 图 | 已完成 | 图表证据已经足够。 |
| 128K long-context boundary test | 128K conservative / near-limit / over-limit live boundary CSV、vLLM launch log、ready check、boundary review | 已完成 | 已完成 128K serving profile 的 live boundary test；512K full-context 仍未完成实机验证。 |
| FP8 KV cache / KV cache quantization | 当前未发现明确 evidence | 未完成 | 不能写已完成。 |

## 4. 量化实验最终解释

本阶段量化闭环的核心结果是：

- baseline：Seed-OSS-36B-Instruct FP32 batch profile；
- optimized：Seed-OSS-36B-Instruct W8A8 compressed-tensors batch profile；
- 两者使用相同 serving 参数：
  - `tensor_parallel_size=2`
  - `max_model_len=512`
  - `max_num_batched_tokens=8192`
  - `max_num_seqs=32`
  - `gpu_memory_utilization=0.90`

实测结果：

- W8A8 在 concurrency=1/2/4/8/16 下，QPS 提升约 31.4% 到 126.1%；
- W8A8 在相同并发下，output tokens/s 提升约 31.4% 到 126.1%；
- W8A8 的 model loading memory 从约 67.59 GiB 降至约 17.71 GiB，降低约 73.8%；
- W8A8 显著扩大了可用 KV cache 空间和并发 headroom；
- runtime `nvidia-smi` 显存占用没有同比下降，原因是 vLLM 会把释放出的模型权重显存重新分配给 KV cache。

因此，报告中应写成：

> W8A8 显著降低模型权重加载显存，并提升 batch serving 吞吐；但在 vLLM serving 场景下，运行时 GPU 总显存不一定下降，因为 vLLM 会利用释放出的显存扩展 KV cache，从而提升并发容量。

不能写成：

> INT8 让运行时总显存降低 30% 以上。

## 5. 当前边界与不可扩展表述

以下内容不能在最终报告里写成“已完成”：

1. 不能写 plain INT8 / AWQ / GPTQ 稳定 serving 已完成；
2. 不能写 Seed-Coder 专项评测已完成；
3. 不能写 512K full-context 已完成；
4. 不能写 FP8 KV cache quantization 已完成；
5. 不能写 runtime `nvidia-smi` 总显存降低超过 30%；
6. 不能把 failed INT8 attempts 包装成成功量化部署；
7. 不能把 W8A8 compressed-tensors 量化与 strict INT8 / AWQ / GPTQ 稳定 serving 完全等同。

## 6. 推荐最终表述

本阶段完成了 Seed-OSS-36B-Instruct 在 2×A100 环境下的 FP32 baseline 与 W8A8 compressed-tensors 量化 serving 对比。实验显示，在相同 batch serving 参数下，W8A8 在 concurrency=1/2/4/8/16 时带来约 31.4% 到 126.1% 的 QPS 与 output tokens/s 提升；模型加载显存由约 67.59 GiB 降至约 17.71 GiB，降低约 73.8%。由于 vLLM 会将释放出的显存用于更大的 KV cache，运行时 `nvidia-smi` 总显存占用没有按同等比例下降，因此本实验将显存收益解释为模型权重加载显存降低和 KV cache/concurrency headroom 提升，而不是简单的总显存下降。strict INT8 相关路径，包括 bitsandbytes、INC 和 compressed-tensors INT8，均已进行可行性探测和失败边界记录，最终选择 W8A8 compressed-tensors 作为稳定、可复现的 8-bit serving 路径。
