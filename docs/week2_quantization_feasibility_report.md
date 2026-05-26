# Seed-OSS-36B 量化优化可行性分析与实验计划

## 1. 背景

本阶段围绕 Seed-OSS-36B-Instruct 推理服务的量化优化可行性展开分析，重点评估不同精度配置对显存占用、延迟和吞吐表现的影响。目标是形成可复现的量化前后性能对比表，包括显存占用、P50/P95 latency、tokens/s、错误率和输出质量观察。

当前项目已完成 Seed-OSS-36B-Instruct 在 RunPod 2×NVIDIA A100-SXM4-80GB 环境下的 BF16 serving baseline、并发 benchmark、64K 长上下文验证和 Prefix Cache 行为分析。本文在该 baseline 基础上，对 FP32、INT8、AWQ/GPTQ、FP8 KV Cache 和低比特 KV cache 压缩等量化路线进行资源可行性分析，并给出后续实验计划。

## 2. 当前 BF16 Baseline

| 项目 | 当前结果 |
|---|---|
| Model | ByteDance-Seed/Seed-OSS-36B-Instruct |
| Serving engine | vLLM 0.11.2 |
| API service | FastAPI + VLLMBackend |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| Precision | BF16 |
| Tensor Parallel Size | 2 |
| Week1 max_model_len | 4096 |
| Week2 max_model_len | 65536 |
| Verified context length | up to 61.9K input tokens |
| Benchmark concurrency | 1 / 2 / 4 / 8 / 16 |
| Observed GPU memory usage | ~75.8GB / 80GB per GPU |

当前 BF16 baseline 已完成以下验证：

1. vLLM 服务成功启动；
2. FastAPI + VLLMBackend + vLLM Server 链路打通；
3. `/health`、`/generate`、FastAPI `/metrics`、vLLM `/metrics` 验证成功；
4. 完成 concurrency = 1 / 2 / 4 / 8 / 16 的 benchmark；
5. 完成 8K、16K、32K、56K、61.9K input tokens 的长上下文请求验证；
6. 保存 vLLM 启动日志、nvidia-smi 输出、metrics snapshot、benchmark CSV 和性能图表。

该 BF16 baseline 是后续量化实验的主要对照组。

## 3. FP32 Baseline 可行性分析

Seed-OSS-36B 约 36B 参数。仅从模型权重存储估算：

| Precision | Bytes / parameter | Estimated weight memory |
|---|---:|---:|
| FP32 | 4 bytes | ~144GB |
| BF16 / FP16 | 2 bytes | ~72GB |
| INT8 | 1 byte | ~36GB |
| INT4 | 0.5 byte | ~18GB |

当前 RunPod 实验环境为 2×A100 80GB，总显存约 160GB。FP32 权重本身约 144GB，尚未计入以下额外开销：

1. KV cache；
2. CUDA graph；
3. vLLM runtime overhead；
4. temporary buffers；
5. tokenizer / API server / framework overhead；
6. tensor parallel communication overhead；
7. 长上下文请求带来的 KV cache 扩张。

因此，在当前 2×A100 80GB 环境下，FP32 serving baseline 缺少足够显存余量，尤其难以同时支持长上下文 KV cache。当前阶段未将 FP32 作为已完成实测结果，而将其记录为资源受限项。

后续若需要进行严格 FP32 baseline，应使用更多 GPU 或更高显存 GPU，并保存以下 evidence：

| Evidence | 内容 |
|---|---|
| vLLM startup log | 启动命令、模型加载过程、失败或成功信息 |
| nvidia-smi | 显存占用、GPU 利用率 |
| error trace | OOM / unsupported / timeout 等错误信息 |
| benchmark CSV | 若启动成功，保存 latency、tokens/s、error rate |
| conclusion | 判断 FP32 baseline 是否具备可复现实测条件 |

## 4. INT8 量化可行性分析

INT8 量化不是简单将 vLLM 启动参数中的 `--dtype` 修改为 `int8`。可部署的 INT8 或低比特推理通常需要：

1. 已量化模型权重；
2. 量化配置文件；
3. vLLM 支持的 quantization backend；
4. 与模型结构兼容的 kernel；
5. 输出质量回归验证；
6. latency、throughput、memory、accuracy 的综合评估。

对于 Seed-OSS-36B-Instruct，当前阶段尚未准备可直接用于 vLLM serving 的 INT8/AWQ/GPTQ 量化权重，也未完成离线量化流程。因此，本文不记录未经实测的 INT8 性能数据，而是将 INT8 作为后续实验路线。

## 5. 当前量化完成度与资源边界

| 原始目标要求 | 当前状态 | 判断 |
|---|---|---|
| BF16 baseline | 已完成真实部署与 benchmark | 已完成 |
| FP32 对比 | 当前 2×A100 80GB 环境显存余量不足 | 需后续资源验证 |
| INT8 量化 | 尚未准备兼容量化权重或离线量化流程 | 需后续实验 |
| 显存降低 ≥30% | 尚未完成真实量化实验 | 当前不声明达成 |
| 速度提升 ≥20% | 尚未完成真实量化实验 | 当前不声明达成 |
| 量化对比表 | 已设计对比表结构 | 待后续实验填充 |
| KV cache 优化路线 | 已完成 KV cache / Prefix Cache 分析 | 可继续推进 FP8 KV Cache |

## 6. 量化路线对比

### 6.1 Weight Quantization

权重量化的主要目标是减少模型权重显存占用，从而提高模型部署可行性，并为 KV cache 释放更多显存空间。

| Route | Target | Current status | Follow-up action |
|---|---|---|---|
| INT8 weight quantization | 降低权重显存 | 未实测 | 准备 Seed-OSS 兼容 INT8 权重或量化流程 |
| AWQ | 低比特权重量化，常用于 LLM serving | 未实测 | 评估 vLLM 与 Seed-OSS 兼容性 |
| GPTQ | 低比特权重量化 | 未实测 | 评估量化流程、加载方式和质量回归 |
| FP8 weight quantization | 降低权重与计算成本 | 未实测 | 评估 GPU 与 vLLM 支持情况 |

### 6.2 KV Cache Quantization

KV cache 是长上下文 serving 的核心显存瓶颈。当前 64K 服务中，vLLM 启动日志显示：

```text
GPU KV cache size: 290,448 tokens
Maximum concurrency for 65,536 tokens per request: 4.43x
```

512K 单请求约需 524,288 tokens。该长度已经超过当前服务报告的 KV cache token capacity。因此，如果后续继续推进 128K、256K、512K，KV cache quantization 或 FP8 KV Cache 比单纯权重量化更直接关联长上下文能力。

| Route | Target | Current status | Follow-up action |
|---|---|---|---|
| FP8 KV Cache | 降低 KV cache memory footprint | 未实测 | 下次 GPU 窗口优先尝试 |
| KV cache quantization with calibration scales | 改善低精度 KV cache 的质量稳定性 | 未实测 | 准备 calibration 数据 |
| Prefix Cache | 加速重复前缀请求 | 已完成行为分析 | 继续区分 cold prompt 与 cached prompt |
| TurboQuant / low-bit KV compression | 前沿低比特 KV cache 压缩路线 | 调研路线 | 不作为当前已实现功能 |

## 7. TurboQuant 路线定位

TurboQuant 等低比特压缩方法可作为后续长上下文推理优化的研究方向。当前项目尚未实现 TurboQuant，也不将其作为已完成实验结果。

在本项目中，TurboQuant 的合理定位是：

```text
当前阶段已完成 vLLM KV cache capacity、Prefix Cache metrics 和重复长文本请求行为分析。后续可调研 TurboQuant 等低比特 KV cache 压缩方法，用于评估其对 128K、256K、512K long-context serving 的潜在帮助。
```

该路线与以下工程问题相关：

1. 长上下文推理的 KV cache 显存瓶颈；
2. 低比特压缩对吞吐和延迟的影响；
3. 长上下文 serving 的显存成本；
4. cached prompt 与 cold prompt 的性能差异；
5. 大规模推理服务中的资源利用率优化。

## 8. 计划中的量化实验设计

后续若重新开启 GPU 实验，应按照以下顺序推进。

### 8.1 FP32 Feasibility Test

目标：确认 FP32 在当前或更高资源环境下是否具备启动条件。

| Item | Record |
|---|---|
| dtype | float32 |
| GPU | 2×A100 80GB or higher |
| Expected result | 可能出现 OOM 或显存余量不足 |
| Evidence | vLLM log, nvidia-smi, error trace |
| Purpose | 明确 FP32 baseline 是否具备实测条件 |

### 8.2 FP8 KV Cache Test

目标：评估 FP8 KV Cache 是否能增加可用 KV cache token capacity，或改善长上下文 serving 的显存效率。

| Item | Record |
|---|---|
| Target | 降低 KV cache 显存占用 |
| Context levels | 64K / 128K / 256K |
| Metrics | KV cache size, max concurrency, latency, tokens/s |
| Evidence | vLLM startup log, benchmark CSV, nvidia-smi |
| Purpose | 验证是否能推进更长上下文 serving |

### 8.3 INT8 / AWQ / GPTQ Serving Test

目标：评估低比特权重量化是否降低模型权重显存占用，并比较其对推理延迟、吞吐和输出质量的影响。

| Item | Record |
|---|---|
| Quantization method | INT8 / AWQ / GPTQ / FP8 |
| Model source | Hugging Face / self-quantized |
| Metrics | memory, P50, P95, tokens/s, error rate |
| Quality check | GSM8K mini eval, codegen mini eval |
| Purpose | 评估低比特权重量化对显存、速度和质量的影响 |

## 9. 量化对比表结构

当前阶段不填入未经实测的数据。后续量化实验完成后，将按照以下结构更新：

| Method | Tested | GPU memory / GPU | P50 latency | P95 latency | tokens/s | Quality observation | Conclusion |
|---|---|---:|---:|---:|---:|---|---|
| FP32 | No | TBD | TBD | TBD | TBD | TBD | Resource feasibility required |
| BF16 | Yes | ~75.8GB | measured | measured | measured | usable | Current baseline |
| INT8 | No | TBD | TBD | TBD | TBD | TBD | Requires quantized weights |
| FP8 KV Cache | No | TBD | TBD | TBD | TBD | TBD | High priority for long context |
| AWQ / GPTQ | No | TBD | TBD | TBD | TBD | TBD | Candidate route |

## 10. 阶段交付边界说明

本阶段原始目标包括 INT8 量化与 FP32 对比。当前阶段已完成：

1. BF16 baseline 的真实部署与 benchmark；
2. 2×A100 80GB 下 Seed-OSS-36B 的显存占用记录；
3. FP32 baseline 的资源可行性分析；
4. INT8/AWQ/GPTQ/FP8 等量化路线拆解；
5. KV cache quantization 与 512K 长上下文之间的关系分析；
6. 后续量化实验设计与对比表结构。

当前阶段尚未完成：

1. FP32 实机启动验证；
2. INT8 实机量化推理；
3. 显存降低 ≥30% 的真实实验数据；
4. 速度提升 ≥20% 的真实实验数据。

因此，当前项目不声明量化优化指标已经达成。后续实验将基于 BF16 baseline 继续补齐真实对比数据。

## 11. Evidence 路径

| Evidence | Path |
|---|---|
| BF16 64K vLLM startup log | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_launch_64k.log` |
| BF16 64K startup key lines | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_64k_key_startup_lines.txt` |
| Long-context summary | `docs/week2_context_gradient_summary.md` |
| 512K feasibility analysis | `docs/week2_512k_feasibility_and_resource_analysis.md` |
| Prefix Cache investigation | `docs/week2_prefix_cache_investigation_summary.md` |
| Performance report | `docs/week2_performance_optimization_report.md` |
| Figures | `figures/` |

## 12. 结论

当前阶段已完成 Seed-OSS-36B-Instruct 的 BF16 serving baseline、并发 benchmark、64K 长上下文验证和 KV cache / Prefix Cache 分析。真实 INT8 与 FP32 对比尚未完成，主要限制来自当前 GPU 显存余量、量化权重准备和框架兼容性验证。

后续量化优化应优先推进：

1. FP32 feasibility test，用于明确高精度 baseline 的资源条件；
2. FP8 KV Cache test，用于验证是否能提升长上下文 KV cache 容量；
3. INT8/AWQ/GPTQ serving test，用于比较低比特权重量化下的显存、延迟、吞吐和输出质量；
4. GSM8K / codegen mini eval，用于评估量化后的质量变化。

该路线能够在不记录未经实测指标的前提下，继续推进 Seed-OSS-36B 推理服务的性能优化工作。