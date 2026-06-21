# Seed-OSS-36B W8A8 量化实验报告

## 1. 实验目标

本实验用于验证 Seed-OSS-36B-Instruct 在真实 2×A100-SXM4-80GB 环境下的低比特权重量化 serving 能力，并对比 FP32 baseline 与 W8A8 compressed-tensors serving 在显存、吞吐、延迟和并发能力上的差异。

本实验重点回答以下问题：

1. Seed-OSS-36B-Instruct 是否可以在 FP32 精度下完成 serving baseline；
2. 是否可以通过离线量化生成 W8A8 compressed-tensors checkpoint；
3. W8A8 量化后是否可以被 vLLM 正常加载并提供 OpenAI-compatible API；
4. 在相同 batch-profile serving 参数下，W8A8 相比 FP32 是否带来可量化的吞吐和延迟收益；
5. 显存收益应该如何客观解释，避免将 vLLM 的 KV cache 复用机制误读为运行时总显存下降；
6. strict INT8、AWQ、GPTQ、INC、bitsandbytes 等路径的边界是什么。

## 2. 实验环境

| 项目 | 配置 |
|---|---|
| 云平台 | RunPod |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理框架 | vLLM 0.11.2 |
| Tensor Parallel Size | 2 |
| API | vLLM OpenAI-compatible API |
| 对照 baseline | FP32 serving |
| 量化方案 | W8A8 compressed-tensors |
| 对比方式 | 同参数 batch-profile benchmark |

本实验使用 FP32 serving 作为对照基线，使用 W8A8 compressed-tensors serving 作为量化优化方案。两组服务均完成了启动、ready check、smoke test 和 concurrency sweep。

## 3. FP32 Baseline

FP32 baseline 已完成实机启动、API ready、smoke test 和 batch-profile benchmark。

FP32 vLLM 启动日志显示：

| 指标 | 数值 |
|---|---:|
| Model loading memory | 67.5901 GiB |
| Available KV cache memory | 9.43 GiB |
| GPU KV cache size | 38,624 tokens |
| Maximum concurrency for 512 tokens/request | 75.44x |

对应 evidence：

- [`logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log`](../logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log)
- [`logs/new_2xa100_seed_oss_fp32_final_inventory_20260528.txt`](../logs/new_2xa100_seed_oss_fp32_final_inventory_20260528.txt)
- [`results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528.csv`](../results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528.csv)
- [`results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv`](../results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv)

## 4. W8A8 compressed-tensors 离线量化与 Serving

本阶段完成了 Seed-OSS-36B-Instruct 的 W8A8 compressed-tensors 离线量化，并成功通过 vLLM 加载量化 checkpoint 进行 serving。

W8A8 vLLM 启动日志显示：

| 指标 | 数值 |
|---|---:|
| Model loading memory | 17.7109 GiB |
| Available KV cache memory | 53.04 GiB |
| GPU KV cache size | 434,480 tokens |
| Maximum concurrency for 512 tokens/request | 848.59x |

对应 evidence：

- [`logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt`](../logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt)
- [`logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log`](../logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log)
- [`logs/new_2xa100_seed_oss_w8a8_ready_evidence_20260528.txt`](../logs/new_2xa100_seed_oss_w8a8_ready_evidence_20260528.txt)
- [`results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528.csv`](../results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528.csv)
- [`results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv`](../results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv)
- [`results/quantized_model_metadata/seed_oss_36b_w8a8/`](../results/quantized_model_metadata/seed_oss_36b_w8a8)

## 5. FP32 vs W8A8 性能对比

两组实验使用相同 batch-profile serving 参数：

| 参数 | 数值 |
|---|---|
| tensor_parallel_size | 2 |
| max_model_len | 512 |
| max_num_batched_tokens | 8192 |
| max_num_seqs | 32 |
| gpu_memory_utilization | 0.90 |
| concurrency sweep | 1 / 2 / 4 / 8 / 16 |
| requests per concurrency | 32 |

核心对比结果如下：

| Concurrency | FP32 QPS | W8A8 QPS | QPS 提升 | FP32 P95 latency | W8A8 P95 latency | P95 降低 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.3117 | 0.4096 | 31.41% | 3.1300s | 2.5703s | 17.88% |
| 2 | 0.5674 | 0.7968 | 40.43% | 4.0014s | 2.5774s | 35.59% |
| 4 | 1.0626 | 1.5286 | 43.85% | 3.7787s | 2.7323s | 27.69% |
| 8 | 1.4671 | 3.1125 | 112.15% | 5.4604s | 2.5973s | 52.43% |
| 16 | 2.6922 | 6.0876 | 126.12% | 6.4298s | 2.6735s | 58.42% |

W8A8 在 concurrency=1/2/4/8/16 下均带来 QPS 和 output tokens/s 提升，提升范围约为 31.4% 到 126.1%。P95 latency 在所有并发设置下均低于 FP32 baseline。

对应 evidence：

- [`results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`](../results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv)
- [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png)
- [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png)
- [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png)

## 6. 显存收益分析

W8A8 的主要显存收益体现在模型权重加载显存下降和 KV cache headroom 增加。

| 指标 | FP32 | W8A8 | 变化 |
|---|---:|---:|---:|
| Model loading memory | 67.5901 GiB | 17.7109 GiB | 下降约 73.8% |
| Available KV cache memory | 9.43 GiB | 53.04 GiB | 增加约 5.63× |
| GPU KV cache size | 38,624 tokens | 434,480 tokens | 增加约 11.25× |
| Maximum concurrency for 512 tokens/request | 75.44x | 848.59x | 增加约 11.25× |

需要注意，vLLM serving 场景下不能简单使用 `nvidia-smi` 运行时总显存占用判断量化节省比例。原因是 vLLM 会将量化释放出的权重显存重新分配给 KV cache，从而提高可服务 token capacity 和并发 headroom。

因此，本实验的显存收益应表述为：

- 模型权重加载显存从 67.5901 GiB 降至 17.7109 GiB；
- 可用 KV cache memory 从 9.43 GiB 增至 53.04 GiB；
- GPU KV cache size 从 38,624 tokens 增至 434,480 tokens；
- 运行时 `nvidia-smi` 总显存不一定同比下降，因为释放出的显存被 serving engine 用于扩展 KV cache。

不能表述为：

- W8A8 让运行时 GPU 总显存占用按同等比例下降；
- 运行时 `nvidia-smi` 显存下降超过 30%。

## 7. strict INT8 / AWQ / GPTQ 路线边界

本阶段除 W8A8 compressed-tensors 量化闭环外，也对 bitsandbytes INT8、INC INT8、compressed-tensors strict INT8、AWQ 和 GPTQ 等路径进行了可行性探测。

结论如下：

| 路线 | 当前状态 | 结论 |
|---|---|---|
| W8A8 compressed-tensors | 已完成 | 已完成离线量化、vLLM serving、smoke test 和 batch-profile benchmark |
| bitsandbytes INT8 | 已完成定向质量复测 / 未形成稳定 serving | 已完成 Transformers + BitsAndBytes runtime quantization 下的 GSM8K 输出预算定向复测；不纳入 vLLM serving 性能闭环 |
| INC INT8 | 已探测 | 对原始 BF16 checkpoint 不能直接形成稳定 serving |
| compressed-tensors strict INT8 | 已探测 | 需要预量化 checkpoint 或明确 quantization_config，不能直接作用于原始 BF16 checkpoint |
| AWQ | 已完成 external artifact serving-stack 验证 | 已完成 vLLM AWQ-Marlin、API smoke 与 GSM8K full evaluation；不纳入 BF16/W8A8 同源质量排名 |
| GPTQ | 未完成 | 尚未通过 artifact、启动、API 与小样本 Gate |
| FP8 KV cache | 已完成近极限容量验证 / 未完成完整性能收益评测 | 已完成 4×A100 下 BF16 KV 与 FP8 KV 的 512K near-limit 容量和 headroom 对照；未形成同一 workload 下的完整性能收益结论 |

对应 evidence：

- [`logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt`](../logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt)
- [`logs/new_2xa100_seed_oss_bnb_int8_final_evidence_20260528.txt`](../logs/new_2xa100_seed_oss_bnb_int8_final_evidence_20260528.txt)
- [`logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt`](../logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt)
- [`logs/new_2xa100_seed_oss_inc_int8_failure_summary_20260528.txt`](../logs/new_2xa100_seed_oss_inc_int8_failure_summary_20260528.txt)
- [`logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt`](../logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt)

## 8. 与优化指标的对应关系

| 指标 | 当前完成情况 | 说明 |
|---|---|---|
| 量化 serving | 已完成 | 完成 W8A8 compressed-tensors 离线量化与 vLLM serving |
| FP32 对比 | 已完成 | 完成 FP32 baseline 与 W8A8 的同参数 batch-profile 对比 |
| 速度提升 ≥20% | 已完成 | QPS 与 output tokens/s 提升约 31.4% 到 126.1% |
| 显存降低 ≥30% | 按 model loading memory 口径完成 | model loading memory 下降约 73.8%；runtime 总显存不作为该指标口径 |
| Batch-profile 对比表 | 已完成 | 已保存 CSV 和图表 |
| strict INT8 / GPTQ | 未形成最终稳定 serving | 已保留兼容性探测和失败边界；AWQ 已单独完成 serving-stack 验证 |
| FP8 KV cache | 已完成容量边界验证 | 容量与理论并发余量已验证；单请求 latency 不作为性能优化结论 |

## 9. Evidence 路径

| Evidence | Path |
|---|---|
| FP32 vLLM launch log | [`logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log`](../logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log) |
| W8A8 vLLM launch log | [`logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log`](../logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log) |
| W8A8 offline quantization inventory | [`logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt`](../logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt) |
| FP32 summary CSV | [`results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv`](../results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv) |
| W8A8 summary CSV | [`results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv`](../results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv) |
| FP32 vs W8A8 improvement CSV | [`results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`](../results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv) |
| QPS figure | [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png) |
| P95 latency figure | [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png) |
| output tokens/s figure | [`figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png`](../figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png) |
| strict INT8 root-cause probe | [`logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt`](../logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt) |
| quantization process appendix | [`logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt`](../logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt) |
| BnB INT8 output-budget summary | [`evidence/week2_hardening/bnb_int8/output_budget_validation/bnb_int8_cap_hit_256_to_768_summary_20260620.json`](../evidence/week2_hardening/bnb_int8/output_budget_validation/bnb_int8_cap_hit_256_to_768_summary_20260620.json) |
| BF16 output-budget summary | [`results/week2_hardening/bf16_controlled/cap_hit_366_max768/gsm8k_bf16_cap_hit_366_max768_summary_20260621.csv`](../results/week2_hardening/bf16_controlled/cap_hit_366_max768/gsm8k_bf16_cap_hit_366_max768_summary_20260621.csv) |
| AWQ GSM8K full summary | [`results/week2_hardening/awq/gsm8k_awq_marlin_full_budget0_max768_20260619_summary.json`](../results/week2_hardening/awq/gsm8k_awq_marlin_full_budget0_max768_20260619_summary.json) |

## 10. 阶段结论

本阶段完成了 Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 环境下的 FP32 baseline 与 W8A8 compressed-tensors 量化 serving 对比。W8A8 在相同 batch-profile serving 参数下，将 QPS 与 output tokens/s 提升约 31.4% 到 126.1%，并将 P95 latency 降低约 17.9% 到 58.4%。

显存方面，W8A8 将 model loading memory 从 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%；available KV cache memory 从 9.43 GiB 增至 53.04 GiB，约 5.63×；GPU KV cache size 从 38,624 tokens 增至 434,480 tokens，约 11.25×。由于 vLLM 会将释放出的显存用于 KV cache，运行时 `nvidia-smi` 总显存不一定同比下降，因此本报告将显存收益定义为模型权重加载显存下降和 KV cache/concurrency headroom 增加。

本阶段稳定、同源且可用于性能与显存对比的 serving 闭环仍为 FP32 baseline vs W8A8 compressed-tensors serving。BitsAndBytes INT8 已完成运行时量化路径下的 GSM8K 输出预算定向复测，但未形成 vLLM serving 性能闭环。BF16/vLLM 已完成全部 366 条历史 output-cap-hit 样本的 `@768` 定向复测；原始 75.7392% accuracy 仅保留为短输出预算下的历史 serving behavior，不作为最终数学推理质量结论。AWQ 已完成外部预量化 artifact 的 vLLM serving-stack 验证与 GSM8K full evaluation，但其 checkpoint provenance、dtype 与 kernel 不同于 BF16/W8A8 主线，不能作为同源量化性能排名。INC INT8、compressed-tensors strict INT8 与 GPTQ 仍保留为兼容性边界或后续优化方向。FP8 KV cache 已完成容量边界验证，但尚未形成统一 workload 下的完整性能收益结论。

## W8A8 @768 定向复测

针对历史 `max_new_tokens=256` 下的 395 条 W8A8 output-cap-hit 样本，完成 `max_new_tokens=768` 定向 serving 复测。395 条请求全部成功，353 条正确，准确率为 89.3671%。与同一批样本历史 `@256` 的 85/395 正确相比，272 条由错误转为正确，表明该子集的大部分错误由输出预算不足引起。

该结果用于修正 output-cap-hit 子集的质量解释，不替代完整 GSM8K full benchmark 的 accuracy。详细协议、transition 与证据路径见 `docs/week2_quantization_protocol_audit.md`。

## 11. 最终解释边界

本报告中的“FP32 baseline”仅沿用历史文件命名。实际 serving 基线为 Seed-OSS-36B-Instruct 的 BF16 vLLM profile；后续正文统一按 BF16 baseline 理解。

BF16 与 W8A8 的性能对比使用相同 workload、多重集合、batch-profile 参数和固定 64-token 输出：两侧各完成 160 条请求，全部 HTTP 200。该 microbenchmark 可用于解释 W8A8 的显存、KV Cache、QPS 与 P95 latency 收益。

历史 BF16 与 W8A8 的 GSM8K full run 不构成严格的量化精度对照。W8A8 adapter 额外加入 system message 与 evaluation instruction，导致全部 1319 条样本固定多出 72 input tokens；同时原始 `max_new_tokens=256` 存在系统性输出截断。因此，历史 accuracy 仅保留为 route-level fixed-budget serving outcome，不解释为纯量化 quality loss。

BnB INT8 用于 Transformers runtime 下的输出预算诊断；AWQ 用于外部 artifact 的 vLLM + AWQ-Marlin serving 验证；GPTQ 尚未形成稳定 serving 产物，不纳入完成结果。
