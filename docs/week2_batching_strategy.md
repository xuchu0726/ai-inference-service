# Week2 Dynamic Batching / Batch Size 测试方案与实测结果

## 1. 文档目的

本文档记录 Week2 中对 vLLM dynamic batching / continuous batching 行为的测试方案与实测结果。

在 vLLM serving 场景中，batch size 不是训练中的固定 batch_size。vLLM 会根据请求队列、KV cache、max_model_len、max_num_batched_tokens 和调度策略动态合并请求。因此，本项目用 concurrency sweep 观察吞吐、延迟和稳定性变化。

核心指标包括：

1. QPS；
2. P50 latency；
3. P95 latency；
4. tokens/s；
5. error_rate；
6. GPU memory；
7. vLLM running / waiting requests；
8. KV cache usage。

---

## 2. 实验配置

| 项目 | 配置 |
|---|---|
| 云平台 | RunPod |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| Serving engine | vLLM 0.11.2 |
| API layer | FastAPI + VLLMBackend |
| Precision | BF16 |
| Tensor Parallel Size | 2 |
| max_model_len | 65536 |
| Endpoint | `http://127.0.0.1:8000/generate` |
| max_new_tokens | 128 |
| temperature | 0.0 |
| thinking_budget | 0 |
| Requests per setting | 40 |
| Tested concurrency | 1 / 2 / 4 / 8 / 16 |

---

## 3. 实测结果

| Concurrency | Requests | Error rate | QPS | Avg latency (s) | P50 latency (s) | P95 latency (s) | Avg tokens/s |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 40 | 0.0 | 0.325 | 3.077 | 3.340 | 3.348 | 38.294 |
| 2 | 40 | 0.0 | 0.659 | 3.033 | 3.313 | 3.320 | 38.586 |
| 4 | 40 | 0.0 | 1.238 | 3.067 | 3.340 | 3.361 | 38.302 |
| 8 | 40 | 0.0 | 2.368 | 3.098 | 3.379 | 3.400 | 37.868 |
| 16 | 40 | 0.0 | 3.848 | 3.204 | 3.507 | 3.532 | 36.602 |

---

## 4. 结果分析

从 concurrency=1 到 concurrency=16，系统 QPS 从 0.325 提升到 3.848，吞吐提升约 11.84 倍。

P95 latency 从 3.348s 上升到 3.532s，增幅约 5.5%。这说明并发提升显著提高了整体吞吐，同时只带来了可控的尾延迟增加。

error rate 在所有并发设置下均为 0，说明当前 FastAPI + VLLMBackend + vLLM 服务链路在该测试范围内保持稳定。

Avg tokens/s 从 38.294 下降到 36.602，说明更高并发下单请求生成速率略有下降。这是合理 trade-off：系统用少量单请求性能损失换取整体 QPS 大幅提升。

---

## 5. 工程结论

本轮测试证明，vLLM continuous batching 能够在 Seed-OSS-36B-Instruct 服务中有效提升吞吐。

当前最重要的量化结论是：

1. concurrency=16 相比 concurrency=1，QPS 提升约 11.84×；
2. P95 latency 仅增加约 5.5%；
3. error rate 保持 0；
4. tokens/s 小幅下降，体现吞吐与单请求速度之间的 trade-off。

这说明当前服务已经不只是单请求 demo，而是具备基础在线 serving 性能分析能力。

---

## 6. Evidence 路径

| Evidence | Path |
|---|---|
| concurrency=1 summary | `results/week2_dynamic_batch_concurrency_1_summary.csv` |
| concurrency=2 summary | `results/week2_dynamic_batch_concurrency_2_summary.csv` |
| concurrency=4 summary | `results/week2_dynamic_batch_concurrency_4_summary.csv` |
| concurrency=8 summary | `results/week2_dynamic_batch_concurrency_8_summary.csv` |
| concurrency=16 summary | `results/week2_dynamic_batch_concurrency_16_summary.csv` |
| GPU snapshot | `logs/week2_nvidia_smi_after_dynamic_batch_sweep.txt` |
| vLLM metrics | `results/week2_vllm_metrics_after_dynamic_batch_sweep.txt` |
| FastAPI metrics | `results/week2_fastapi_metrics_after_dynamic_batch_sweep.txt` |
| Evidence package | `artifacts/week2_seed_oss_gsm8k_codegen_dynamic_batch_evidence_20260518_042845.tar.gz` |

---

## 7. max_num_batched_tokens 补充调优实验

在基础 concurrency sweep 之后，本项目进一步完成了 vLLM `max_num_batched_tokens` 专项调优实验，覆盖 4096、8192、16384、32768 四组配置，并进一步比较 short-output burst 与 long-output decode-heavy 两类 workload。

专项报告见：

- `docs/week2_batch_token_tuning_report.md`

核心结果如下：

| Workload | 对比配置 | 关键结果 | 工程结论 |
|---|---|---|---|
| short_output_c8 burst | 8192 vs 32768 | QPS 1.921 提升至 2.371；P95 latency 7.350s 降至 3.415s | 短输出 burst 场景更适合 32768 profile |
| long_output_c4 decode-heavy | 8192 vs 32768 | 8192 的 P95 latency 为 13.258s，32768 为 16.406s | 长输出或 mixed workload 更适合较保守的 8192 profile |

该结果说明，`max_num_batched_tokens` 不存在对所有 workload 都最优的单一取值。更合理的工程方案是维护 workload-aware serving profile，并在后续网关层根据请求类型、输出长度和运行时指标进行路由。

当前结论应表述为 profile 级别的 batch-token 调优和 workload-aware batching policy foundation，不应表述为已经实现完整生产级运行时动态批处理调度器。

## 8. 后续计划

后续可在当前实验基础上继续推进：

1. 实现轻量级 workload classification 与 routing policy abstraction；
2. 在资源允许时测试更多 max_num_seqs、GPU memory utilization 和 prefix cache 配置；
3. 将 batch-token profile 结论接入 Week3 的网关路由、降级策略和高可用设计；
4. 在 Week4 压测中继续验证不同 workload profile 下的 QPS、P95/P99 latency、error_rate 和资源边界。
