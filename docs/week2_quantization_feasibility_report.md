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

- `logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log`
- `logs/new_2xa100_seed_oss_fp32_final_inventory_20260528.txt`
- `results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528.csv`
- `results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv`

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

- `logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt`
- `logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log`
- `logs/new_2xa100_seed_oss_w8a8_ready_evidence_20260528.txt`
- `results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528.csv`
- `results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv`
- `results/quantized_model_metadata/seed_oss_36b_w8a8/`

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

- `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`
- `figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png`
- `figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png`
- `figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png`

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
| bitsandbytes INT8 | 已探测 | 可作为 online low-bit loading 探测，但不能作为最终 strict INT8 指标闭环 |
| INC INT8 | 已探测 | 对原始 BF16 checkpoint 不能直接形成稳定 serving |
| compressed-tensors strict INT8 | 已探测 | 需要预量化 checkpoint 或明确 quantization_config，不能直接作用于原始 BF16 checkpoint |
| AWQ / GPTQ | 未完成稳定 serving | 当前没有形成可复现 serving 闭环 |
| FP8 KV cache | 未完成 | 与长上下文 KV cache capacity 强相关，但本阶段未完成实机验证 |

对应 evidence：

- `logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt`
- `logs/new_2xa100_seed_oss_bnb_int8_final_evidence_20260528.txt`
- `logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt`
- `logs/new_2xa100_seed_oss_inc_int8_failure_summary_20260528.txt`
- `logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt`

## 8. 与优化指标的对应关系

| 指标 | 当前完成情况 | 说明 |
|---|---|---|
| 量化 serving | 已完成 | 完成 W8A8 compressed-tensors 离线量化与 vLLM serving |
| FP32 对比 | 已完成 | 完成 FP32 baseline 与 W8A8 的同参数 batch-profile 对比 |
| 速度提升 ≥20% | 已完成 | QPS 与 output tokens/s 提升约 31.4% 到 126.1% |
| 显存降低 ≥30% | 按 model loading memory 口径完成 | model loading memory 下降约 73.8%；runtime 总显存不作为该指标口径 |
| Batch-profile 对比表 | 已完成 | 已保存 CSV 和图表 |
| strict INT8 / AWQ / GPTQ | 未形成最终稳定 serving | 已保留兼容性探测和失败边界 |
| FP8 KV cache | 未完成 | 不作为本阶段完成项 |

## 9. Evidence 路径

| Evidence | Path |
|---|---|
| FP32 vLLM launch log | `logs/new_2xa100_seed_oss_fp32_vllm_launch_20260528.log` |
| W8A8 vLLM launch log | `logs/new_2xa100_seed_oss_w8a8_vllm_launch_20260528.log` |
| W8A8 offline quantization inventory | `logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt` |
| FP32 summary CSV | `results/new_2xa100_seed_oss_fp32_batchprofile_concurrency_sweep_20260528_summary.csv` |
| W8A8 summary CSV | `results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv` |
| FP32 vs W8A8 improvement CSV | `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv` |
| QPS figure | `figures/week2/quantization/seed_oss_fp32_vs_w8a8_qps.png` |
| P95 latency figure | `figures/week2/quantization/seed_oss_fp32_vs_w8a8_p95_latency.png` |
| output tokens/s figure | `figures/week2/quantization/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png` |
| strict INT8 root-cause probe | `logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt` |
| quantization process appendix | `logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt` |

## 10. 阶段结论

本阶段完成了 Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 环境下的 FP32 baseline 与 W8A8 compressed-tensors 量化 serving 对比。W8A8 在相同 batch-profile serving 参数下，将 QPS 与 output tokens/s 提升约 31.4% 到 126.1%，并将 P95 latency 降低约 17.9% 到 58.4%。

显存方面，W8A8 将 model loading memory 从 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%；available KV cache memory 从 9.43 GiB 增至 53.04 GiB，约 5.63×；GPU KV cache size 从 38,624 tokens 增至 434,480 tokens，约 11.25×。由于 vLLM 会将释放出的显存用于 KV cache，运行时 `nvidia-smi` 总显存不一定同比下降，因此本报告将显存收益定义为模型权重加载显存下降和 KV cache/concurrency headroom 增加。

本阶段未将 bitsandbytes INT8、INC INT8、compressed-tensors strict INT8、AWQ、GPTQ 或 FP8 KV cache 包装为已完成稳定 serving。相关探测保留为兼容性边界和后续优化方向。最终可复现、可对比、可写入性能报告的量化闭环为 FP32 baseline vs W8A8 compressed-tensors serving。
