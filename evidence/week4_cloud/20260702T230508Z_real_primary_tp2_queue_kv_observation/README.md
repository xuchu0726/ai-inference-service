# 真实 primary TP=2 调度队列与 KV Cache 指标观测

## 实验对象
- primary：Seed-OSS-36B W8A8，TP=2，API :8002。
- 服务配置：`max_num_seqs=16`、`max_num_batched_tokens=8192`。
- 请求：32 并发，长 prompt，`max_tokens=512`。
- 路径：直接请求 primary vLLM API，不经过 Gateway fallback/breaker。

## 结果
- completed=32，failed=0。
- peak_running=16，peak_waiting=16。
- peak_kv_cache_usage_perc=0.02412404501147869。
- p50_latency_s=38.265989，max_latency_s=38.308691。

## 结论与边界
- 实际运行请求数达到 `max_num_seqs=16`，同时出现 16 条等待请求，证明 primary TP=2 的调度上限触发了服务端排队。
- 同时采集到真实 KV Cache usage 指标；峰值约 2.41%，未接近 KV Cache 容量瓶颈。
- 本证据支持动态 batching/queueing 与 runtime metrics 链路，不证明 KV Cache saturation、真实 GPU OOM 或 Gateway 层吞吐。
