# 第 2 周性能优化报告：Seed-OSS-36B 推理服务性能分析与模型特性验证

## 1. 本周目标

第 2 周目标是在第 1 周已完成 Seed-OSS-36B-Instruct 基础部署、FastAPI 封装、vLLM 接入、Thinking Budget 参数链路和 Prometheus 基础监控的基础上，进一步推进推理服务的性能分析与优化验证。

本周重点从“服务跑通”升级为“性能可观测、瓶颈可分析、优化有数据支撑”。

核心工作包括：

1. 使用 Prometheus + Grafana 分析推理服务指标、GPU 使用情况和内存瓶颈；
2. 扩展并发性能测试，统计 QPS、P50/P95 latency、tokens/s 和 error_rate；
3. 做上下文长度梯度测试，分析 context length 对显存、KV Cache、延迟和吞吐的影响；
4. 评估 Seed-OSS-36B 量化优化路径，形成 BF16 baseline 与可落地量化方案的对比；
5. 结合 GQA 与 KV Cache 机制解释长上下文和高并发下的性能变化；
6. 补充 GSM8K 数学推理与代码生成场景验证；
7. 完成 FAQ、API 错误码和边界情况说明，提升服务可维护性。

---

## 2. Week1 基线回顾

第 1 周已完成以下基线能力：

| 项目 | 当前状态 |
|---|---|
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理引擎 | vLLM 0.11.2 |
| API 层 | FastAPI |
| 后端适配 | VLLMBackend |
| GPU | 2×NVIDIA A100-SXM4-80GB |
| dtype | bfloat16 |
| Tensor Parallel | TP=2 |
| max_model_len | 4096 |
| max_num_batched_tokens | 8192 |
| FastAPI metrics | 已接入 |
| vLLM metrics | 已验证 |
| Thinking Budget | 512 / 1024 已验证 |
| 初步并发测试 | concurrency=2 / 4 |
| 稳定运行显存 | 约 75.8GB / 80GB per GPU |

Week1 结论：

1. Seed-OSS-36B-Instruct 已完成基础服务化部署；
2. FastAPI + VLLMBackend + vLLM Server 架构可用；
3. 当前 4K context 下 BF16 TP=2 配置可运行；
4. 显存压力已经较高，后续长上下文和更高并发必须逐步测试；
5. 512K full-context 不应直接硬冲，需要先做上下文长度梯度测试和资源边界分析。

---

## 3. Week2 交付范围

本周交付分为 7 类。

### 3.1 监控与可观测性

目标：

1. 配置 Prometheus scrape；
2. 搭建或记录 Grafana dashboard；
3. 展示 FastAPI、vLLM 和 GPU 相关指标；
4. 为本阶段性能瓶颈分析提供数据来源。

关注指标：

| 类型 | 指标 |
|---|---|
| FastAPI | request count, request latency, status code |
| vLLM | running requests, waiting requests, KV cache usage, prefix cache |
| GPU | memory used, utilization, memory utilization |
| Benchmark | QPS, P50, P95, tokens/s, error_rate |

本周新增监控采样脚本：

| 脚本 | 作用 | 产出 |
|---|---|---|
| `scripts/sample_gpu_metrics.sh` | 使用 `nvidia-smi` 定时采样 GPU 显存、GPU utilization、memory utilization | `logs/week2_nvidia_smi_sampling.csv` |
| `scripts/snapshot_vllm_metrics.py` | 抓取 vLLM `/metrics` 中的 running requests、waiting requests、KV Cache usage、prefix cache 指标 | `results/week2_vllm_metrics_snapshot.txt` |

GPU 采样命令示例：

    bash scripts/sample_gpu_metrics.sh logs/week2_nvidia_smi_sampling.csv 5

vLLM metrics 快照命令示例：

    python scripts/snapshot_vllm_metrics.py \
      --url http://127.0.0.1:8002/metrics \
      --output results/week2_vllm_metrics_snapshot.txt

本周已保存 Prometheus 配置、Grafana dashboard JSON、Grafana live load probe 截图、vLLM metrics 快照和 `nvidia-smi` 采样文件，用于分析 GPU 利用率、显存瓶颈、KV Cache 压力、Prefix Cache 命中和请求排队行为。

---

### 3.2 并发 / Batch 性能测试

目标：

测试不同并发度下服务吞吐、尾延迟和稳定性变化。

实验配置：

| concurrency | max_new_tokens | thinking_budget | 说明 |
|---:|---:|---:|---|
| 1 | 128 | 512 | 单请求基线 |
| 2 | 128 | 512 | 小并发 |
| 4 | 128 | 512 | Week1 已验证，Week2 复测 |
| 8 | 128 | 512 | 中等并发 |
| 16 | 128 | 512 | 高阶尝试 |

记录指标：

1. total_requests；
2. successful_requests；
3. failed_requests；
4. error_rate；
5. QPS；
6. client_latency_avg；
7. client_latency_p50；
8. client_latency_p95；
9. tokens_per_second_avg；
10. GPU memory；
11. vLLM running/waiting requests；
12. KV cache usage。

已完成图表：

1. QPS vs concurrency；
2. P95 latency vs concurrency；
3. tokens/s vs concurrency；
4. error_rate vs concurrency；
5. GPU memory vs concurrency。

---


### 3.2.1 max_num_batched_tokens 专项调优

在基础并发测试之后，本项目进一步对 vLLM 的 `max_num_batched_tokens` 参数进行了专项调优分析。该参数会影响 vLLM 调度阶段可容纳的 token budget，从而影响 batch formation、请求等待、吞吐和尾延迟。

本轮实验覆盖 4096、8192、16384、32768 四组配置，并进一步区分 short-output burst 与 long-output decode-heavy 两类 workload。结果显示，`max_num_batched_tokens` 不存在对所有 workload 都最优的单一取值，应根据请求形态选择不同 serving profile。

| Workload | 对比配置 | 关键结果 | 工程结论 |
|---|---|---|---|
| short_output_c8 burst | 8192 vs 32768 | QPS 1.921 提升至 2.371；P95 latency 7.350s 降至 3.415s | 短输出 burst 场景更适合 32768 profile |
| long_output_c4 decode-heavy | 8192 vs 32768 | 8192 的 P95 latency 为 13.258s，32768 为 16.406s | 长输出或 mixed workload 更适合较保守的 8192 profile |

该实验说明，生产化 dynamic batching 不应简单理解为运行时热修改单个 vLLM engine 参数。由于 `max_num_batched_tokens` 属于启动时调度参数，更合理的工程设计是维护多个 serving profile，并在网关层根据 workload 类型进行路由。

专项报告路径：

- `docs/week2_batch_token_tuning_report.md`

相关 evidence：

- `results/week2_batch_tokens_workload_summary_20260525.csv`
- `results/week2_batch_tokens_short_c8_wave_latency_summary_20260526.csv`
- `figures/week2/batch_tokens/week2_batch_tokens_profile_decision.png`
- `figures/week2/batch_tokens/week2_batch_tokens_workload_qps_summary.png`
- `figures/week2/batch_tokens/week2_batch_tokens_workload_p95_summary.png`


### 3.3 上下文长度梯度测试

目标：

回应 Week1 中 max_model_len=4096 与 Seed-OSS 原生 512K 能力差距较大的问题，用分阶段实验分析长上下文下的显存、延迟、KV Cache 压力和稳定性边界。

本周已完成两组长上下文实验：

1. 64K serving profile 下的上下文长度梯度测试；
2. 128K serving profile 下的长上下文边界验证。

64K 实验使用 `max_model_len=65536`，完成 8K、16K、32K、56K 和 61.9K input tokens 级别请求。首次梯度测试显示，随着输入 tokens 从 7,434 增长到 56,303，client latency 从 4.81s 增长到 16.13s，tokens/s 从 26.69 下降到 7.94，符合长上下文 prefill 成本上升预期。

128K 实验使用 `max_model_len=131072`、`max_num_seqs=1` 的边界 profile，完成 conservative、near-limit 和 over-limit 三类请求：

| Case | Input tokens | Status | Client latency (s) | 结论 |
|---|---:|---|---:|---|
| 128K conservative | 126,222 | 200 / success | 84.350549 | 成功处理接近 128K 的长上下文请求 |
| 128K near-limit | 130,608 | 200 / success | 10.089885 | 成功逼近 131,072 token 上限，但受 prefix cache / warm state 影响 |
| 128K over-limit | 134,991 | 400 / rejected | 0.191030 | 超过上下文上限后被 vLLM 明确拒绝，系统没有 OOM 或崩溃 |

需要说明的是，512K full-context 仍未完成实机验证。当前项目已经从 Week1 的 4K 基线推进到 64K 梯度测试和 128K 边界验证，但 512K 单请求仍需要更多 GPU、KV cache compression、FP8 KV cache 或更强资源配置支撑，因此本阶段只作为后续资源验证方向。

---

### 3.4 量化优化可行性与对比

原始目标要求：

    INT8 量化，对比 FP32 精度下的速度与显存占用。

当前资源边界：

在后续 2×A100-SXM4-80GB 实验窗口中，项目已完成 Seed-OSS-36B-Instruct 的 FP32 baseline serving、W8A8 compressed-tensors 离线量化、W8A8 vLLM serving、smoke test 和同参数 batch-profile benchmark。FP32 与 W8A8 对比不再停留在资源估算阶段，而是已有可复现的实测 CSV、启动日志、ready evidence 和图表。

本周实际完成情况：

1. 已完成 BF16 serving baseline，并作为主服务基线；
2. 已完成 FP32 baseline serving、smoke test 和 batch-profile benchmark；
3. 已完成 W8A8 compressed-tensors 离线量化、vLLM serving 和同参数 batch-profile benchmark；
4. 已保存 FP32 与 W8A8 的 QPS、P95 latency、output tokens/s、model loading memory 和运行边界证据；
5. 已记录 bitsandbytes INT8、INC INT8 和 compressed-tensors strict INT8 路线的兼容性探测与失败边界；
6. 最终稳定量化闭环采用 FP32 baseline vs W8A8 compressed-tensors serving，而不是包装为 plain INT8 / AWQ / GPTQ 全部完成。

量化对比表结构：

| 方案 | 是否完成 | 当前结论 | 备注 |
|---|---|---|---|
| BF16 baseline | 已完成 | 已完成真实部署、长上下文、并发、GSM8K full 和 codegen mini eval | 当前主基线 |
| FP32 serving | 已完成 | 已完成 2×A100-SXM4-80GB 下的 FP32 baseline serving、smoke test 和 batch-profile benchmark | 作为 W8A8 对照基线 |
| W8A8 compressed-tensors | 已完成 | 已完成离线量化、vLLM serving、smoke test 和同参数 batch-profile 对比 | 当前稳定可复现的 8-bit 权重量化路径 |
| strict INT8 / AWQ / GPTQ | 部分完成 / 有边界 | bitsandbytes INT8、INC INT8、compressed-tensors strict INT8 均已做可行性探测和失败边界记录，但没有形成最终稳定 serving | 本阶段不作为最终量化闭环 |
| FP8 KV Cache | 未完成 | 与长上下文 KV cache 显存优化强相关 | 后续优先级较高 |

---

### 3.5 KV Cache 与 GQA 分析

目标：

结合 Week2 的并发和上下文长度实验，解释 GQA 和 KV Cache 如何影响 Seed-OSS-36B 的推理性能。

重点分析：

1. GQA 如何减少 key/value head 数量；
2. GQA 如何降低 KV Cache 显存压力；
3. 上下文长度增长时 KV Cache usage 如何变化；
4. concurrency 增加时 running/waiting requests 如何变化；
5. P95 latency 上升是否来自排队、prefill、decode 或显存压力。

---

### 3.6 GSM8K 数学推理验证

目标：

验证 Seed-OSS-36B 在数学推理任务上的服务稳定性、结果正确性和端到端延迟表现。

本轮已完成 GSM8K test set full benchmark。最终结果为 1319 个样本全部 API 成功，API error rate 为 0，正确 999 个，accuracy 为 75.74%，P50 latency 为 5.51s，P95 latency 为 6.69s。该结果可作为后续量化、降级策略和质量回归实验的任务级 baseline。

---

### 3.7 代码生成验证

目标：

验证当前 FastAPI + VLLMBackend + Seed-OSS-36B-Instruct 服务链路是否能够支持基础代码生成场景。

本轮已完成 5 个 Python 代码生成 mini eval，全部 API 成功，并全部通过简单正确性检查。该测试覆盖加法、奇偶判断、字符串反转、阶乘和单词计数等基础函数生成任务。该结果不能替代 HumanEval、MBPP 或 Seed-Coder 专项评测，但可以证明当前服务链路具备代码生成场景的基础可用性。

---

## 4. Week2 新增文档

为回应 Week1 反馈，本周新增：

1. `docs/troubleshooting_faq.md`
2. `docs/api_error_codes.md`

这两份文档用于提升服务的可维护性和可排查性。

---

## 5. 实验结果索引

本节索引 Week2 已完成实验结果与对应 evidence 路径。

### 5.1 并发 benchmark

已完成文件：

    evidence/week2_64k_context/results/week2_concurrency_c1_summary.csv
    evidence/week2_64k_context/results/week2_concurrency_c2_summary.csv
    evidence/week2_64k_context/results/week2_concurrency_c4_summary.csv
    evidence/week2_64k_context/results/week2_concurrency_c8_summary.csv
    evidence/week2_64k_context/results/week2_concurrency_c16_summary.csv

### 5.2 上下文长度 benchmark

已完成文件：

    results/week2_context_gradient_summary.csv
    docs/week2_context_gradient_summary.md
    results/week2_context_length_8k_on_64k_service.csv
    results/week2_context_length_16k_on_64k_service.csv
    results/week2_context_length_32k_on_64k_service.csv
    results/week2_context_length_64k_conservative_on_64k_service.csv
    results/week2_context_length_64k_near_limit_on_64k_service.csv
    results/week2_context_repeat_r1_56k_then_64k.csv
    results/week2_context_repeat_r2_64k_then_56k.csv
    results/week2_context_repeat_r3_56k_then_64k.csv
    results/new_2xa100_seed_oss_128k_conservative_context_test_20260529.csv
    results/new_2xa100_seed_oss_128k_near_limit_context_test_20260529.csv
    results/new_2xa100_seed_oss_128k_over_limit_context_test_20260529.csv
    docs/week2/seed_oss_128k_context_boundary_review.md

### 5.3 量化可行性

已完成文件：

    results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv
    docs/week2_quantization_feasibility_report.md
    docs/week2_requirement_compliance_matrix.md

### 5.4 GSM8K

已完成文件：

    results/week2_gsm8k_full_seed_oss_budget0_summary.csv

### 5.5 代码生成

已完成文件：

    results/week2_codegen_mini_seed_oss_budget0.csv

### 5.6 图表

已完成图表：

    figures/week2_qps_vs_concurrency_report.png
    figures/week2_latency_p50_p95_vs_concurrency.png
    figures/week2_tokens_per_second_vs_concurrency_report.png
    figures/week2_error_rate_vs_concurrency_report.png
    figures/week2_context_latency_first_pass_only.png
    figures/week2_context_tokens_per_second_first_pass_only.png
    figures/week2_prefix_cache_repeat_latency.png
    results/figures/seed_oss_fp32_vs_w8a8_qps.png
    results/figures/seed_oss_fp32_vs_w8a8_p95_latency.png
    results/figures/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png

---

## 6. Seed-OSS-36B 长上下文性能验证（RunPod 2×A100 80GB）

### 6.1 实验环境

本轮长上下文实验在 RunPod 云端 GPU 环境完成，核心配置如下：

| Item | Value |
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

- `Using max model len 65536`
- `GPU KV cache size: 290,448 tokens`
- `Maximum concurrency for 65,536 tokens per request: 4.43x`
- FastAPI `/health`、vLLM `/v1/models`、vLLM `/metrics` 均验证成功。

### 6.2 长上下文梯度测试结果

| Context | Input tokens | Output tokens | Client latency (s) | Server latency (s) | Tokens/s | Status | Note |
|---|---:|---:|---:|---:|---:|---|---|
| 8K | 7434 | 128 | 4.811523 | 4.796601 | 26.6856 | 200 / True | first-pass |
| 16K | 15297 | 128 | 5.439229 | 5.435553 | 23.5487 | 200 / True | first-pass |
| 32K | 30465 | 128 | 8.570771 | 8.566287 | 14.9423 | 200 / True | first-pass |
| 56K | 56303 | 128 | 16.128279 | 16.122442 | 7.9392 | 200 / True | first-pass / cold-ish |
| 61.9K | 61917 | 128 | 7.437081 | 7.432070 | 17.2227 | 200 / True | near-limit, cache-affected |

### 6.3 结果分析

8K、16K、32K、56K 的首次测试结果显示，随着输入 token 数从 7,434 增长到 56,303，client latency 从 4.81s 增长到 16.13s，tokens/s 从 26.69 下降到 7.94。这符合长上下文推理中 prefill 成本上升的预期。

但 61.9K near-limit 测试出现了低于 56K 的 latency，不能直接解释为上下文越长性能越好。后续交替复测显示，56K 与 61.9K 在重复请求后 latency 均稳定在约 4.2s 左右，结合 vLLM `prefix_cache_hits_total` 与 `prefix_cache_queries_total` 的变化，可以判断该现象主要来自 prefix cache、warm state 和重复 prompt 结构。

因此，本报告将长上下文结果分为两类解释：

1. 首次梯度测试：用于观察上下文长度增长对 latency 和 tokens/s 的影响。
2. 重复长文档测试：用于验证 vLLM prefix cache 对重复前缀场景的加速效果。

### 6.4 Prefix Cache 复测结论

复测前后 vLLM metrics 显示，prefix cache 查询与命中量显著增长。重复测试期间 prefix cache 命中率较高，说明相似长文本请求会明显受缓存状态影响。

这对生产推理服务有直接意义：

- 对重复系统 prompt、重复合同模板、重复知识库前缀的场景，prefix cache 可以降低重复 prefill 成本。
- 对完全不同的长文档请求，不能用缓存命中后的 latency 代表冷启动长上下文性能。
- 长上下文 benchmark 必须区分 cold prompt、warm prompt、prefix-cache-hit prompt，否则结果会被误读。


### 6.5 Evidence 文件索引

本节实验对应的原始证据已归档到 GitHub 仓库，主要文件如下：

| Evidence | Path |
|---|---|
| 64K vLLM 启动日志 | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_launch_64k.log` |
| 64K vLLM 启动关键行 | `evidence/week2_64k_context/logs/week2_seed_oss_vllm_64k_key_startup_lines.txt` |
| FastAPI 64K 日志 | `evidence/week2_64k_context/logs/week2_fastapi_vllm_64k.log` |
| 8K context result | `evidence/week2_64k_context/results/week2_context_length_8k_on_64k_service.csv` |
| 16K context result | `evidence/week2_64k_context/results/week2_context_length_16k_on_64k_service.csv` |
| 32K context result | `evidence/week2_64k_context/results/week2_context_length_32k_on_64k_service.csv` |
| 56K context result | `evidence/week2_64k_context/results/week2_context_length_64k_conservative_on_64k_service.csv` |
| 61.9K near-limit result | `evidence/week2_64k_context/results/week2_context_length_64k_near_limit_on_64k_service.csv` |
| Prefix cache repeat round 1 | `evidence/week2_64k_context/results/week2_context_repeat_r1_56k_then_64k.csv` |
| Prefix cache repeat round 2 | `evidence/week2_64k_context/results/week2_context_repeat_r2_64k_then_56k.csv` |
| Prefix cache repeat round 3 | `evidence/week2_64k_context/results/week2_context_repeat_r3_56k_then_64k.csv` |
| Prefix cache before metrics | `evidence/week2_64k_context/results/week2_vllm_metrics_before_context_repeat_investigation.txt` |
| Prefix cache after metrics | `evidence/week2_64k_context/results/week2_vllm_metrics_after_context_repeat_investigation.txt` |
| GPU sampling log | `evidence/week2_64k_context/logs/week2_nvidia_smi_sampling_64k_context.csv` |
| 原始压缩证据包 | `artifacts/week2_64k_context_evidence_20260514_005638.tar.gz` |


### 6.6 报告图表索引

本节实验图表已保存到 `figures/` 目录。图表使用原则如下：

- 并发性能图使用 1/2/4/8/16 concurrency 的真实 FastAPI + vLLM benchmark summary。
- 长上下文趋势图只使用 first-pass/cold-ish 数据点：8K、16K、32K、56K。
- 61.9K near-limit 结果受到 prefix cache 与 warm state 影响，不并入 cold-ish 趋势图，而单独通过 prefix cache repeat 图解释。

| Figure | Path | Purpose |
|---|---|---|
| QPS vs concurrency | `figures/week2_qps_vs_concurrency_report.png` | 展示 concurrency 提升带来的吞吐提升 |
| P50/P95 latency vs concurrency | `figures/week2_latency_p50_p95_vs_concurrency.png` | 展示并发增加下的尾延迟变化 |
| Tokens/s vs concurrency | `figures/week2_tokens_per_second_vs_concurrency_report.png` | 展示单请求生成速率随并发变化的 trade-off |
| Error rate vs concurrency | `figures/week2_error_rate_vs_concurrency_report.png` | 展示并发测试下 error rate 保持 0 |
| Long-context latency first-pass | `figures/week2_context_latency_first_pass_only.png` | 展示 8K/16K/32K/56K 首次长上下文 latency 趋势 |
| Long-context tokens/s first-pass | `figures/week2_context_tokens_per_second_first_pass_only.png` | 展示首次长上下文 tokens/s 下降趋势 |
| Prefix cache repeat latency | `figures/week2_prefix_cache_repeat_latency.png` | 展示重复长文本请求在 prefix cache/warm state 下的 latency 变化 |
| FP32 vs W8A8 QPS | `results/figures/seed_oss_fp32_vs_w8a8_qps.png` | 展示 W8A8 量化 serving 相比 FP32 baseline 的吞吐提升 |
| FP32 vs W8A8 P95 latency | `results/figures/seed_oss_fp32_vs_w8a8_p95_latency.png` | 展示 W8A8 量化 serving 对尾延迟的改善 |
| FP32 vs W8A8 output tokens/s | `results/figures/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png` | 展示量化前后生成吞吐变化 |


### 6.7 关键图表

#### 并发吞吐与延迟

![QPS vs concurrency](../figures/week2_qps_vs_concurrency_report.png)

![P50/P95 latency vs concurrency](../figures/week2_latency_p50_p95_vs_concurrency.png)

![Tokens/s vs concurrency](../figures/week2_tokens_per_second_vs_concurrency_report.png)

![Error rate vs concurrency](../figures/week2_error_rate_vs_concurrency_report.png)

#### 长上下文首次梯度测试

![Long-context latency first-pass](../figures/week2_context_latency_first_pass_only.png)

![Long-context tokens/s first-pass](../figures/week2_context_tokens_per_second_first_pass_only.png)

#### Prefix Cache 复测

![Prefix cache repeat latency](../figures/week2_prefix_cache_repeat_latency.png)


## 7. FP32 vs W8A8 量化性能对比

本阶段完成了 Seed-OSS-36B-Instruct 的 FP32 baseline serving 与 W8A8 compressed-tensors 量化 serving 对比。两组实验使用相同 batch-profile serving 参数，并在 concurrency=1/2/4/8/16 下进行 benchmark。

| Concurrency | FP32 QPS | W8A8 QPS | QPS 提升 | FP32 P95 latency | W8A8 P95 latency | P95 降低 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.3117 | 0.4096 | 31.41% | 3.1300s | 2.5703s | 17.88% |
| 2 | 0.5674 | 0.7968 | 40.43% | 4.0014s | 2.5774s | 35.59% |
| 4 | 1.0626 | 1.5286 | 43.85% | 3.7787s | 2.7323s | 27.69% |
| 8 | 1.4671 | 3.1125 | 112.15% | 5.4604s | 2.5973s | 52.43% |
| 16 | 2.6922 | 6.0876 | 126.12% | 6.4298s | 2.6735s | 58.42% |

W8A8 在所有并发设置下均提升 QPS 和 output tokens/s，提升范围约为 31.4% 到 126.1%。P95 latency 也在所有并发设置下低于 FP32 baseline，说明该量化路径不仅降低模型权重加载显存，也改善了 batch serving 吞吐与尾延迟。

![FP32 vs W8A8 QPS](../results/figures/seed_oss_fp32_vs_w8a8_qps.png)

![FP32 vs W8A8 P95 latency](../results/figures/seed_oss_fp32_vs_w8a8_p95_latency.png)

![FP32 vs W8A8 output tokens/s](../results/figures/seed_oss_fp32_vs_w8a8_output_tokens_per_second.png)

显存方面，FP32 baseline 的 model loading memory 为 67.5901 GiB，W8A8 为 17.7109 GiB，下降约 73.8%。同时，available KV cache memory 从 9.43 GiB 提升到 53.04 GiB，GPU KV cache size 从 38,624 tokens 提升到 434,480 tokens。该收益应解释为模型权重加载显存降低与 KV cache/concurrency headroom 增加，而不是运行时 `nvidia-smi` 总显存同比下降。

## 8. 当前风险与处理策略

| 风险 | 影响 | 处理策略 |
|---|---|---|
| strict INT8 / AWQ / GPTQ 路径未稳定服务化 | 本阶段不作为最终稳定 serving 闭环 | 保留兼容性探测和失败边界，最终采用已跑通的 FP32 vs W8A8 compressed-tensors 量化闭环 |
| 32K/64K OOM | 长上下文实验失败 | 保留 OOM 边界，降低 context length |
| 高并发 timeout | benchmark 失败率上升 | 保留失败样本，降低 concurrency 或增加 timeout |
| Grafana 长期监控留存不足 | 不能证明长时间生产级监控稳定性 | 当前已保存 Prometheus 配置、Grafana dashboard JSON 和 live load probe evidence；长期 TSDB 留存不作为本阶段完成项 |
| GPU 成本过高 | 试错成本增加 | 先本地准备脚本和报告框架，再集中跑 GPU |

---

## 9. 阶段结论

本周完成了 Seed-OSS-36B-Instruct 推理服务在真实云端 GPU 环境下的性能优化与模型特性验证。系统采用 FastAPI + VLLMBackend + vLLM Server 三层架构，模型侧使用 vLLM 0.11.2、BF16、Tensor Parallel Size = 2，在 2 × NVIDIA A100-SXM4-80GB 上完成部署和验证。

核心实验结论如下：

1. 并发能力方面，在固定 128 output tokens 的条件下，concurrency 从 1 提升到 16 时，系统 QPS 从 0.325 提升到 3.848，吞吐提升约 11.84×；P95 latency 从 3.348s 上升到 3.532s，增幅约 5.5%；error rate 保持 0。结果说明 vLLM continuous batching 能有效提升吞吐，但会带来可控的单请求延迟与单请求 tokens/s 下降。

2. 长上下文能力方面，Seed-OSS-36B-Instruct 在 `max_model_len=65536` 配置下成功完成 8K、16K、32K、56K 以及 61.9K input tokens 级别的推理请求。首次梯度测试中，输入 tokens 从 7,434 增长到 56,303 时，client latency 从 4.81s 增长到 16.13s，tokens/s 从 26.69 下降到 7.94，符合长上下文 prefill 成本上升预期。

3. Prefix Cache 分析方面，61.9K near-limit 请求出现低于 56K 的 latency。通过交替复测和 vLLM metrics 分析，该现象主要来自 prefix cache、warm state 和重复 prompt 结构影响，不能解释为纯冷启动长上下文性能。该问题已在报告中单独建模并保留原始证据。

4. 量化优化方面，本阶段完成 FP32 baseline 与 W8A8 compressed-tensors serving 的同参数 batch-profile 对比。W8A8 将 QPS 与 output tokens/s 提升约 31.4% 到 126.1%，P95 latency 降低约 17.9% 到 58.4%，model loading memory 从 67.5901 GiB 降至 17.7109 GiB，下降约 73.8%。

5. 监控与证据链方面，本周保存了 FastAPI health/metrics、vLLM `/metrics`、vLLM 启动日志、nvidia-smi 采样、benchmark CSV、图表和 evidence 压缩包。所有关键证据已归档到 `evidence/`、`artifacts/`、`results/` 和 `figures/` 目录，并提交到 GitHub。

6. 工程局限方面，当前实验已完成 BF16 baseline、FP32 baseline、W8A8 compressed-tensors serving、FP32 vs W8A8 batch-profile 对比、并发测试、KV cache/prefix cache 分析、128K serving profile 边界验证、GSM8K full benchmark 和代码生成 mini eval。strict INT8 / AWQ / GPTQ 稳定 serving、FP8 KV cache、512K full-context 和 Seed-Coder 专项模型部署仍未完成。

综上，Week2 已从简单 API 验证推进到真实大模型推理服务性能分析阶段，形成了可复现的部署脚本、测试脚本、原始实验数据、图表和工程解释。该阶段结果可作为后续 Week3 高可用架构、降级策略、多模态接入和 Week4 压测验收的基础。

