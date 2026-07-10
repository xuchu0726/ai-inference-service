# Week2 Seed-OSS-36B 512K 长上下文可行性与资源分析

> **历史阶段记录（2026-06-24）**：本文主要记录早期 2×A100 环境下的资源分析与可行性判断。后续已在 4×A100、TP=4、`max_model_len=524288` 下完成 BF16 KV 与 FP8 KV 的约 500K prompt tokens near-limit 真机验证。当前结论以 `docs/week2_performance_optimization_report.md` 和 `docs/week2_hardening_response_summary.md` 为准。


## 1. 背景

Week1 交付中，Seed-OSS-36B-Instruct 以 `max_model_len=4096` 完成基础推理验证。该配置能够验证 FastAPI API 链路、VLLMBackend、Thinking Budget 参数传递和基础 serving 能力，但距离 Seed-OSS 原生 512K 长上下文能力仍有明显差距。

Week2 围绕该问题进行了长上下文能力扩展实验，目标是在真实云端 GPU 环境下尽可能提升 `max_model_len`，并保存可复现 evidence。

## 2. 已完成的实测结果

本轮实验在 RunPod 2×NVIDIA A100-SXM4-80GB 环境下完成。

| 项目 | 配置 |
|---|---|
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| Serving engine | vLLM 0.11.2 |
| Model | ByteDance-Seed/Seed-OSS-36B-Instruct |
| Precision | BF16 |
| Tensor parallel size | 2 |
| max_model_len | 65536 |
| FastAPI backend | VLLMBackend |
| Thinking Budget | 512 |

vLLM 启动日志显示：

```text
Using max model len 65536
GPU KV cache size: 290,448 tokens
Maximum concurrency for 65,536 tokens per request: 4.43x
```

在该配置下，已完成以下长上下文验证：

| Context | Input tokens | Output tokens | Client latency (s) | Status |
|---|---:|---:|---:|---|
| 8K | 7,434 | 128 | 4.811523 | success |
| 16K | 15,297 | 128 | 5.439229 | success |
| 32K | 30,465 | 128 | 8.570771 | success |
| 56K | 56,303 | 128 | 16.128279 | success |
| 61.9K | 61,917 | 128 | 7.437081 | success, cache-affected |

其中 61.9K near-limit 结果受到 Prefix Cache 与 warm state 影响，已在 `docs/week2_prefix_cache_investigation_summary.md` 中单独解释。

## 3. 为什么当前没有直接验证 512K

512K 长上下文对应单请求约 524,288 tokens。当前 64K 服务启动时，vLLM 报告的 GPU KV cache size 为 290,448 tokens。该数值低于 512K 单请求所需 token 数，因此在当前 2×A100 80GB、BF16、TP=2 配置下，直接稳定验证 512K 单请求缺少充分资源余量。

此外，Seed-OSS-36B BF16 权重本身已经占用大量显存。Week1/Week2 实测中，模型加载与 KV cache 预分配后，每张 A100 80GB 显存占用约 75.8GB/80GB，显存余量非常有限。继续提高 `max_model_len` 会进一步增加 KV cache 压力，并显著提高 OOM 风险。

因此，当前项目不能声明“512K 已实测通过”。

准确表述应为：

```text
项目已将 Seed-OSS-36B-Instruct 的实测上下文能力从 Week1 的 4K 提升到 Week2 的 64K 级别，并完成最高约 61.9K input tokens 的真实推理请求验证。512K 属于 Seed-OSS 的原生能力目标，但在当前 2×A100 80GB、BF16、vLLM TP=2 配置下尚未完成实机验证。
```

## 4. 512K 后续可行路线

| 方向 | 作用 | 风险 |
|---|---|---|
| 增加 GPU 数量，例如 4×/8×A100 80GB | 提高 tensor parallel 能力和可用 KV cache 空间 | 成本显著增加 |
| 使用 H100/H200 等更高显存 GPU | 提供更高显存容量和带宽 | 资源成本更高 |
| KV cache quantization | 降低长上下文 KV cache 显存占用 | 需要验证 vLLM 与 Seed-OSS 兼容性 |
| FP8 KV cache | 降低 KV cache memory footprint，提升长上下文可行性 | 需要下次 GPU 窗口实测 |
| 权重量化，例如 AWQ/GPTQ/FP8 | 降低模型权重占用，释放 KV cache 空间 | 需要量化权重或量化流程 |
| 分阶段上下文测试：128K → 256K → 512K | 明确资源边界 | 每个阶段都需要独立启动与证据保存 |
| Prefix Cache / Prompt Cache 优化 | 加速重复前缀场景 | 不能代表 cold prompt 512K 性能 |
| TurboQuant 等前沿 KV cache 压缩路线 | 作为低比特 KV cache 压缩的研究方向，可用于后续方案调研 | 当前项目尚未实现，不能作为已完成实验结果 |

## 5. 对 Week1 待改进点的回应

Week1 待改进点指出：当前 `max_model_len=4096` 与 Seed-OSS 原生 512K 能力差距较大。

Week2 已完成以下改进：

1. 将可运行服务配置从 `max_model_len=4096` 提升到 `max_model_len=65536`。
2. 完成 8K、16K、32K、56K、61.9K input tokens 级别的实测请求。
3. 保存 vLLM 启动日志、KV cache size、nvidia-smi、FastAPI/vLLM metrics、benchmark CSV 和图表。
4. 对 61.9K latency 异常进行了 Prefix Cache 复测与解释。
5. 明确记录当前资源下 512K 尚未完成验证的工程原因和后续可行路线。

## 6. 工程分析价值

该分析不是简单解释“为什么没做到 512K”，而是体现以下工程能力：

1. 能根据模型规模、精度、GPU 显存和 KV cache 容量判断长上下文服务边界；
2. 能区分模型原生能力、serving 配置能力和实机验证能力；
3. 能避免伪造 benchmark，保留真实资源约束和失败边界；
4. 能提出后续优化路径，包括更多 GPU、KV cache quantization、FP8 KV cache、权重量化和前沿低比特压缩方法；
5. 能把长上下文问题从“能不能跑”拆解为显存、KV cache、吞吐、延迟、缓存命中和成本之间的系统权衡。

这类分析更接近真实 AI Infra / LLM serving 工作，而不是简单 API demo。

## 7. Evidence 路径

| Evidence | Path |
|---|---|
| 64K vLLM 启动日志 | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_launch_64k.log` |
| 64K vLLM 启动关键行 | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_64k_key_startup_lines.txt` |
| 64K vLLM model metadata | `evidence/week2_64k_context/results/week2_seed_oss_vllm_64k_models.json` |
| 长上下文结果汇总 | `results/week2_context_gradient_summary.csv` |
| Prefix Cache 分析 | `docs/week2_prefix_cache_investigation_summary.md` |
| 原始证据包 | `artifacts/week2_64k_context_evidence_20260514_005638.tar.gz` |

## 8. 后续 GPU 验证路线

如果后续继续申请或租用 GPU，应按照以下顺序推进，避免直接跳到 512K 导致资源浪费或证据不可解释：

1. 在当前代码基础上尝试 `max_model_len=131072`，记录启动是否成功、KV cache size、显存占用和失败日志；
2. 如果 128K 成功，再尝试 256K；
3. 如果 256K 失败，保存 OOM / capacity failure evidence，并分析是否需要增加 GPU 或启用 KV cache quantization；
4. 若资源允许，尝试 FP8 KV cache 或其他 KV cache compression 路线；
5. 512K 只在资源和配置具备足够余量时实测，不在当前 2×A100 80GB BF16 TP=2 配置下伪造结果。

## 9. 结论

当前 Week2 已经从 4K 基线推进到 64K 级别真实长上下文验证。512K 仍是后续目标，但需要更多 GPU 资源、KV cache 压缩、FP8 KV cache 或权重量化等优化手段配合。项目选择保留真实实验边界，而不是伪造 512K 结果。
