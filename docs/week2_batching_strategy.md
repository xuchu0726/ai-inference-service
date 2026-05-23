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

## 7. 后续计划

本轮实验固定使用当前 64K 服务配置，没有额外重启服务测试不同 max_num_batched_tokens。后续若继续推进 batch 参数优化，应测试：

1. max_num_batched_tokens = 4096；
2. max_num_batched_tokens = 8192；
3. max_num_batched_tokens = 16384；
4. max_num_batched_tokens = 32768。

每组需要记录启动日志、显存占用、QPS、P95 latency、tokens/s、error_rate 和 vLLM KV cache usage。
