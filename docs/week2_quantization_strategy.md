# Week2 量化优化方案：Seed-OSS-36B 推理显存与吞吐对比

## 1. 文档目的

本文档说明 Week2 中如何验证 Seed-OSS-36B-Instruct 的量化优化路线，并对比不同精度/量化方案对显存、延迟、吞吐和输出质量的影响。

Week2 任务要求中明确提出：

1. 实施 Seed-OSS 的 INT8 量化；
2. 对比 FP32 精度下的速度与显存占用；
3. 输出量化前后性能对比表；
4. 目标为显存降低 ≥30%，速度提升 ≥20%。

本项目需要在真实资源约束下完成该要求，因此必须区分：

1. 理论 FP32 baseline；
2. 实际可运行 BF16 baseline；
3. 可落地量化方案；
4. 无法直接落地时的兼容性和资源原因。

---

## 2. 当前资源边界

Week1 已验证配置：

| 项目 | 配置 |
|---|---|
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| GPU | 2×NVIDIA A100-SXM4-80GB |
| dtype | bfloat16 |
| Tensor Parallel | TP=2 |
| max_model_len | 4096 |
| max_num_batched_tokens | 8192 |
| 稳定运行显存 | 约 75.8GB / 80GB per GPU |

该结果说明：

1. BF16 baseline 已经接近单卡显存上限；
2. FP32 权重理论显存约为 BF16 的 2 倍；
3. 在当前 2×A100 80GB 环境下，FP32 serving baseline 很可能不可直接运行；
4. Week2 不能虚假宣称 FP32 已完成，必须用显存估算和运行证据说明资源边界。

---

## 3. Baseline 定义

### 3.1 实际运行 baseline：BF16

实际性能 baseline 使用 Week1/Week2 可运行配置：

    dtype=bfloat16
    tensor_parallel_size=2
    max_model_len=4096
    max_num_batched_tokens=8192

记录指标：

1. GPU memory；
2. QPS；
3. P50/P95 latency；
4. tokens/s；
5. error_rate；
6. 输出质量观察。

### 3.2 理论对照 baseline：FP32

FP32 用于任务书要求中的精度对照，但当前资源可能不足以直接 serving。

估算方式：

    36B parameters × 4 bytes ≈ 144GB 权重显存

还需要额外显存用于：

1. KV Cache；
2. CUDA context；
3. vLLM runtime；
4. activation / temporary tensors；
5. communication buffer；
6. batch / concurrency memory。

因此，FP32 实际 serving 需求会高于 144GB，2×A100 80GB 在当前配置下风险极高。

如果后续资源允许，可以尝试 FP32 小上下文 smoke test；如果无法运行，应记录资源原因和失败日志。

---

## 4. 量化候选方案

Week2 重点评估以下方案：

| 方案 | 说明 | 优先级 |
|---|---|---|
| INT8 | 任务书指定方向，优先检查可行性 | P0 |
| FP8 | 新 GPU / 新推理栈中常见的推理压缩方向 | P1 |
| AWQ | 常见权重量化方案，需确认模型与 vLLM 兼容 | P1 |
| GPTQ | 常见权重量化方案，需确认权重格式和 vLLM 兼容 | P1 |
| KV Cache quantization | 长上下文显存优化方向，作为后续候选 | P2 |

---

## 5. 实验矩阵

| 实验组 | dtype / quantization | 是否必须跑通 | 目标 |
|---|---|---|---|
| BF16 baseline | bfloat16 | 是 | 建立实际性能基线 |
| FP32 estimate / attempt | float32 | 尽量尝试，资源不足则估算 | 回应 FP32 对照要求 |
| INT8 | INT8 或等价支持方案 | 优先尝试 | 验证显存与速度收益 |
| FP8/AWQ/GPTQ | 可用则尝试 | 可选增强 | 作为 INT8 不兼容时替代方案 |

---

## 6. 对比指标

每个可运行方案记录：

1. model_name；
2. dtype / quantization；
3. GPU 数量；
4. max_model_len；
5. max_num_batched_tokens；
6. concurrency；
7. GPU memory used；
8. QPS；
9. P50 latency；
10. P95 latency；
11. tokens/s；
12. error_rate；
13. 输出质量观察；
14. 是否 OOM；
15. 是否 timeout。

---

## 7. 量化对比表模板

| 方案 | 是否跑通 | GPU memory | QPS | P95 latency | tokens/s | 显存变化 | 速度变化 | 质量观察 | 备注 |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
| BF16 baseline | 待填 | 待填 | 待填 | 待填 | 待填 | baseline | baseline | 待填 | 实际主基线 |
| FP32 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 资源不足则写估算 |
| INT8 | 待填 | 待填 | 待填 | 待填 | 待填 | 目标 ≥30% | 目标 ≥20% | 待填 | 优先尝试 |
| FP8/AWQ/GPTQ | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 待填 | 替代方案 |

---

## 8. 失败情况记录原则

如果 INT8、FP32 或其他量化方案无法运行，不能删除失败记录。必须保留：

1. 启动命令；
2. stderr/stdout；
3. vLLM log；
4. nvidia-smi；
5. error message；
6. 失败原因分类；
7. 后续可行替代方案。

失败原因分类：

1. 显存不足；
2. 权重格式不兼容；
3. vLLM 不支持该量化方式；
4. Seed-OSS remote code / chat template 不兼容；
5. CUDA / torch / kernel 版本不兼容；
6. 下载或模型权限问题。

---

## 9. 与 Week2 任务要求的对应关系

| Week2 要求 | 本方案对应 |
|---|---|
| INT8 量化 | 优先检查并尝试 INT8 或 vLLM 可落地等价方案 |
| 对比 FP32 精度下速度与显存 | 给出 FP32 资源估算，资源允许时尝试 FP32 smoke test |
| 量化前后性能对比表 | 使用 BF16/FP32/INT8/FP8/AWQ/GPTQ 表格统一对比 |
| 显存降低 ≥30% | 作为量化目标指标记录 |
| 速度提升 ≥20% | 作为量化目标指标记录 |
| 性能优化报告 | 将结果写入 Week2 主报告 |

---

## 10. 小结

Week2 量化路线的原则是：最大化尝试，但不虚假宣称。

当前最可靠的实际 baseline 是 BF16。FP32 是任务书指定对照，但在 Seed-OSS-36B 与 2×A100 80GB 条件下大概率存在资源瓶颈。INT8/FP8/AWQ/GPTQ 是 Week2 需要优先验证的优化方向。

最终交付不是只写“量化可行”，而是给出可复现命令、运行结果、显存/延迟/吞吐对比、失败日志和资源边界说明。
