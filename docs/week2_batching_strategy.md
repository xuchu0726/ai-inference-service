# Week2 Dynamic Batching / Batch Size 测试方案

## 1. 文档目的

本文档说明 Week2 中如何在 vLLM 推理服务中验证动态 Batch 调度、Batch Size 对吞吐和延迟的影响。

在 vLLM serving 场景中，Batch Size 不等同于传统训练中的固定 batch_size。vLLM 会根据在线请求队列、可用 KV Cache、max_num_batched_tokens、max_model_len 和调度策略进行动态 batching / continuous batching。

因此，本项目使用以下变量近似分析 Batch 行为：

1. concurrency；
2. max_num_batched_tokens；
3. max_model_len；
4. max_new_tokens；
5. vLLM running requests；
6. vLLM waiting requests；
7. KV Cache usage；
8. QPS / P95 / tokens/s / error_rate。

---

## 2. 测试变量

### 2.1 并发度 concurrency

用于模拟同时到达的请求数量。

计划测试：

    1 / 2 / 4 / 8 / 16

观察指标：

1. QPS 是否提升；
2. P95 是否恶化；
3. tokens/s 是否稳定；
4. error_rate 是否上升；
5. waiting requests 是否增加。

---

### 2.2 max_num_batched_tokens

`max_num_batched_tokens` 控制 vLLM 一次调度中允许处理的最大 token 数，是影响 batching、吞吐、显存和延迟的重要参数。

计划测试：

    4096 / 8192 / 16384

说明：

1. 较小值通常降低单次调度显存压力，但可能限制吞吐；
2. 较大值可能提高吞吐，但会增加 activation memory 和尾延迟风险；
3. 对 Seed-OSS-36B，必须结合 GPU memory 和 KV Cache usage 观察。

---

## 3. 推荐实验矩阵

| 实验组 | max_num_batched_tokens | concurrency | 目的 |
|---|---:|---:|---|
| baseline | 8192 | 1/2/4/8 | 复现 Week1/Week2 基线 |
| lower batch tokens | 4096 | 1/2/4/8 | 观察更保守调度下的延迟与显存 |
| higher batch tokens | 16384 | 1/2/4/8 | 观察更激进调度下的吞吐与尾延迟 |

---

## 4. 记录指标

每组实验需要记录：

1. total_requests；
2. successful_requests；
3. failed_requests；
4. error_rate；
5. throughput_qps；
6. client_latency_p50；
7. client_latency_p95；
8. tokens_per_second_avg；
9. GPU memory used；
10. GPU utilization；
11. vLLM num_requests_running；
12. vLLM num_requests_waiting；
13. vLLM kv_cache_usage_perc。

---

## 5. 图表要求

Week2 报告中至少生成以下图表：

1. QPS vs concurrency；
2. P95 latency vs concurrency；
3. tokens/s vs concurrency；
4. error_rate vs concurrency；
5. max_num_batched_tokens vs QPS；
6. max_num_batched_tokens vs P95 latency；
7. max_num_batched_tokens vs GPU memory。

---

## 6. 与 Week2 任务要求的对应关系

| Week2 要求 | 本方案对应 |
|---|---|
| 动态 Batch 调度 | 使用 concurrency + max_num_batched_tokens 观察 vLLM 调度行为 |
| 平衡吞吐量与延迟 | 对比 QPS、P95、tokens/s |
| Batch Size 测试图表 | 生成 max_num_batched_tokens 与 QPS/P95/GPU memory 图表 |
| KV Cache 优化 | 结合 kv_cache_usage_perc 观察缓存压力 |
| 性能优化报告 | 将实验结果写入 Week2 主报告 |

---

## 7. 注意事项

1. 不直接把 vLLM 的 batching 等同于训练 batch size；
2. 不只看 QPS，也要看 P95 和 error_rate；
3. 如果 higher max_num_batched_tokens 触发 OOM 或 timeout，应保留失败日志；
4. 对 Seed-OSS-36B，应优先保证服务稳定，再逐步增加 batching 参数；
5. Batch 测试必须和 GPU/vLLM metrics 采样同时进行。
