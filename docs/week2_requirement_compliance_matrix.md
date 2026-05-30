# Week2 交付完成度与证据索引

## 1. 总体结论

本文件用于将 Week2 性能优化与 Seed 模型特性验证工作，对应到当前仓库中已经完成的实验、代码、日志、图表和文档证据。

当前阶段已经形成以下核心闭环：

- Prometheus / Grafana / vLLM metrics / nvidia-smi 监控证据；
- Seed-OSS-36B-Instruct FP32 serving baseline；
- Seed-OSS-36B-Instruct W8A8 compressed-tensors 离线量化与 vLLM serving；
- FP32 batch profile 与 W8A8 batch profile 的同参数并发对比；
- batch-token profile tuning 与 workload-aware routing abstraction；
- KV cache、Prefix Cache 和 PagedAttention 行为分析；
- GSM8K full benchmark；
- Seed-OSS-36B-Instruct 代码生成 mini eval；
- 64K 长上下文梯度测试、128K serving profile 边界验证和 512K 可行性分析；
- QPS、P95 latency、output tokens/s、error rate、显存和 KV cache 相关图表。

当前阶段的边界包括：

- strict INT8、AWQ、GPTQ 尚未形成稳定 serving 闭环；
- 代码生成验证基于 Seed-OSS-36B-Instruct 完成，Seed-Coder 专项模型部署与评测尚未纳入本阶段交付；
- 512K full-context 尚未完成实机验证，当前完成的是 64K 梯度测试和 128K serving profile 边界验证；
- FP8 KV cache / KV cache quantization 尚未完成实机验证；
- 显存收益以 model loading memory 下降、available KV cache memory 增加和 concurrency headroom 扩大为主要口径，不以运行时 GPU 总显存占用同比下降作为结论。

## 2. 推荐阅读顺序

| 阅读目的 | 推荐文档 |
|---|---|
| 快速了解 Week2 完成内容 | `docs/week2_delivery_summary.md` |
| 核对交付项、完成度和证据路径 | `docs/week2_requirement_compliance_matrix.md` |
| 查看完整性能分析 | `docs/week2_performance_optimization_report.md` |
| 查看 batch-token 调优实验 | `docs/week2_batch_token_tuning_report.md` |
| 查看量化实验与 FP32/W8A8 对比 | `docs/week2_quantization_feasibility_report.md` |
| 查看监控、Prometheus、Grafana 和 GPU 证据 | `docs/week2_observability_report.md` |
| 查看 GSM8K 与代码生成评测 | `docs/week2_eval_mini_report.md` |
| 查看 128K 长上下文边界实验 | `docs/week2/seed_oss_128k_context_boundary_review.md` |

## 3. Week2 交付项逐项映射

| 交付项 | 当前完成情况 | 关键证据 | 完成状态 |
|---|---|---|---|
| Prometheus + Grafana 分析 GPU 利用率和内存瓶颈 | 已接入 FastAPI metrics、vLLM metrics、Prometheus scrape config、Grafana dashboard JSON，并保存 Grafana live load probe、nvidia-smi snapshot 和采样文件。当前分析显示，2×A100 80GB 下主要瓶颈是显存常驻占用与 KV cache capacity，而不是单次请求期间的 GPU 计算利用率。 | `docs/week2_observability_report.md`；`deployment/monitoring/prometheus_week2.yml`；`deployment/monitoring/grafana_week2_seed_oss_dashboard.json`；`figures/week2/observability/week2_grafana_seed_oss_live_load_probe.png` | 已完成 |
| Seed-OSS 低比特量化与 FP32 对比 | 已完成 FP32 baseline serving、W8A8 compressed-tensors 离线量化、W8A8 vLLM serving、smoke test 和同参数 batch-profile benchmark。W8A8 是本阶段稳定可复现的 8-bit 权重量化 serving 路线。 | `docs/week2_quantization_feasibility_report.md`；`results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv` | 已完成 |
| 量化前后性能对比表 | 已形成 FP32 vs W8A8 对比表，覆盖 concurrency=1/2/4/8/16 下的 QPS、P95 latency、tokens/s 和 error rate。W8A8 在 QPS 与 output tokens/s 上提升约 31.4% 到 126.1%。 | `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv` | 已完成 |
| 显存降低指标 | W8A8 将 model loading memory 从 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%。available KV cache memory 从 9.43 GiB 增至 53.04 GiB，GPU KV cache size 从 38,624 tokens 增至 434,480 tokens。由于 vLLM 会将释放出的显存重新分配给 KV cache，运行时 GPU 总显存占用不作为本阶段显存收益口径。 | `logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log`；`logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log` | 按 model loading memory 口径完成 |
| strict INT8 / AWQ / GPTQ 路线探测 | bitsandbytes INT8、INC INT8 和 compressed-tensors strict INT8 已完成兼容性探测和失败边界记录。AWQ/GPTQ 尚未形成稳定 serving 闭环。本阶段最终采用 W8A8 compressed-tensors 作为稳定量化路径。 | `logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt`；`logs/new_2xa100_seed_oss_bnb_int8_final_evidence_20260528.txt`；`logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt`；`logs/new_2xa100_seed_oss_inc_int8_failure_summary_20260528.txt` | 已完成路线边界记录 |
| 动态 Batch 调度 | 已完成 `max_num_batched_tokens` profile-level tuning，覆盖 4096、8192、16384、32768，并区分 short-output burst 与 long-output decode-heavy workload。实验结论已沉淀为 workload-aware routing policy abstraction。 | `docs/week2_batch_token_tuning_report.md`；`docs/week2_routing_policy_abstraction.md`；`app/routing.py`；`tests/test_routing.py` | 已完成 profile-level 调优 |
| Batch Size / batch-token 测试图表 | 已保存 workload QPS summary、P95 summary、profile decision、first-wave latency、wave-level latency 等图表。 | `figures/week2/batch_tokens/` | 已完成 |
| KV 缓存优化与分析 | 当前基于 vLLM PagedAttention、KV cache 和 Prefix Cache 机制进行启用、观测和分析。64K 长上下文、Prefix Cache repeat 和 128K 边界实验均提供了 KV cache 行为证据。 | `docs/week2_performance_optimization_report.md`；`docs/week2_prefix_cache_investigation_summary.md`；`docs/week2/seed_oss_128k_context_boundary_review.md` | 已完成分析闭环 |
| GQA 如何降低计算复杂度 | 文档已解释 GQA 通过减少 key/value heads 降低 KV cache 显存压力，并结合长上下文和并发 serving 场景解释其对推理资源消耗的影响。 | `docs/week2_performance_optimization_report.md`；`docs/week2_512k_feasibility_and_resource_analysis.md` | 已完成 |
| GSM8K 数学推理验证 | 已完成 GSM8K test set 全量评测。1319 个样本全部 API 成功，正确 999 个，accuracy 为 75.74%，P50 latency 为 5.51s，P95 latency 为 6.69s。 | `docs/week2_eval_mini_report.md`；`results/week2_gsm8k_full_seed_oss_budget0_summary.csv` | 已完成 |
| 代码生成验证 | 已完成 5 个 Python 代码生成 mini eval，全部 API 成功，并通过简单正确性检查。该实验用于验证当前 Seed-OSS-36B-Instruct serving 链路支持基础代码生成场景。Seed-Coder 专项模型部署与评测尚未纳入本阶段交付。 | `docs/week2_eval_mini_report.md`；`results/week2_codegen_mini_seed_oss_budget0.csv` | 已完成基础代码生成验证 |
| QPS、延迟、P95 优化图表 | 已覆盖并发性能图、batch-token 调优图和 FP32 vs W8A8 量化对比图。 | `figures/week2/concurrency/week2_qps_vs_concurrency_report.png`；`figures/week2/concurrency/week2_latency_p50_p95_vs_concurrency.png`；`figures/week2/batch_tokens/`；`figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png`；`figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png` | 已完成 |
| 性能优化报告 | 主报告已整合并发测试、长上下文、Prefix Cache、batch-token tuning、FP32 vs W8A8 量化、GSM8K、代码生成、监控证据和阶段边界。 | `docs/week2_performance_optimization_report.md` | 已完成 |
| 64K / 128K 长上下文增强验证 | 已完成 64K serving profile 下的 8K/16K/32K/56K/61.9K 测试，并完成 128K serving profile conservative / near-limit / over-limit 边界验证。该部分用于回应 Week1 中 4K context 与 Seed-OSS 原生 512K 能力之间的差距。 | `docs/week2_context_gradient_summary.md`；`docs/week2/seed_oss_128k_context_boundary_review.md`；`results/new_2xa100_seed_oss_128k_*_20260529.csv` | 已完成阶段性增强 |
| 512K full-context | 当前完成 512K 可行性分析，尚未完成 512K 单请求实机验证。 | `docs/week2_512k_feasibility_and_resource_analysis.md` | 后续资源验证方向 |
| FP8 KV cache / KV cache quantization | 当前完成 KV cache 与 Prefix Cache 分析，尚未完成 FP8 KV cache 实机验证。 | `docs/week2_observability_report.md`；`docs/week2_performance_optimization_report.md` | 后续优化方向 |

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

实测结果如下：

- W8A8 在 concurrency=1/2/4/8/16 下，QPS 提升约 31.4% 到 126.1%；
- W8A8 在相同并发下，output tokens/s 提升约 31.4% 到 126.1%；
- W8A8 的 model loading memory 从 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%；
- available KV cache memory 从 9.43 GiB 增至 53.04 GiB；
- GPU KV cache size 从 38,624 tokens 增至 434,480 tokens；
- runtime `nvidia-smi` 总显存占用不会同比下降，原因是 vLLM 会将释放出的权重显存重新分配给 KV cache。

因此，本阶段的显存收益表述为：

> W8A8 显著降低模型权重加载显存，并提升 batch serving 吞吐；在 vLLM serving 场景下，运行时 GPU 总显存不一定下降，因为 vLLM 会利用释放出的显存扩展 KV cache，从而提升并发容量。

本阶段不使用“运行时 GPU 总显存降低 30% 以上”作为结论口径。

## 5. 当前阶段范围与后续方向

当前阶段已经完成 Seed-OSS-36B-Instruct 的 BF16/FP32/W8A8 serving、并发性能测试、batch-token 调优、64K/128K 长上下文验证、GSM8K full benchmark 和代码生成 mini eval。以下内容作为后续扩展方向保留：

1. strict INT8、AWQ 和 GPTQ 路线已完成兼容性探测，但尚未形成稳定 serving 闭环；
2. 代码生成验证基于 Seed-OSS-36B-Instruct 完成，Seed-Coder 专项模型部署与评测尚未纳入本阶段交付；
3. 512K full-context 尚未完成实机验证，当前已完成 64K 梯度测试和 128K serving profile 边界验证；
4. FP8 KV cache / KV cache quantization 尚未完成实机验证；
5. 显存收益主要体现为 model loading memory 下降、available KV cache memory 增加和 concurrency headroom 扩大，而不是运行时 GPU 总显存占用同比下降；
6. W8A8 compressed-tensors 是本阶段稳定可复现的 8-bit 权重量化 serving 路线，AWQ、GPTQ 和 FP8 KV cache 仍作为后续优化方向。

## 6. 推荐最终表述

本阶段完成了 Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 环境下的 FP32 baseline 与 W8A8 compressed-tensors 量化 serving 对比。实验显示，在相同 batch serving 参数下，W8A8 在 concurrency=1/2/4/8/16 时带来约 31.4% 到 126.1% 的 QPS 与 output tokens/s 提升；模型加载显存由 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%。由于 vLLM 会将释放出的显存用于更大的 KV cache，运行时 GPU 总显存占用没有按同等比例下降，因此本实验将显存收益解释为模型权重加载显存降低和 KV cache/concurrency headroom 提升，而不是简单的总显存下降。strict INT8 相关路径，包括 bitsandbytes、INC 和 compressed-tensors INT8，均已进行可行性探测和失败边界记录，最终选择 W8A8 compressed-tensors 作为稳定、可复现的 8-bit serving 路径。
