# Week2 Seed-OSS-36B 可观测性与资源瓶颈分析报告

## 1. 背景

Week2 性能优化任务要求使用 Prometheus 和 Grafana 等系统监控工具分析 AI 推理服务的 GPU 利用率、显存瓶颈、请求延迟、错误率和服务状态。

当前项目已完成 Seed-OSS-36B-Instruct 在 RunPod 2×NVIDIA A100-SXM4-80GB 环境下的 BF16 serving baseline、并发 benchmark、64K 长上下文验证、Prefix Cache 分析和 Grafana live load probe evidence。本文总结本阶段已完成的可观测性接入、已保存的 metrics evidence、GPU 资源分析结论和监控边界。

## 2. 服务架构

本阶段推理服务采用三层结构：

```text
Client / Benchmark Script
        |
        v
FastAPI /generate
        |
        v
VLLMBackend
        |
        v
vLLM OpenAI-Compatible Server
        |
        v
Seed-OSS-36B-Instruct on 2×A100 80GB
```

关键端口：

| Service | Port | Purpose |
|---|---:|---|
| FastAPI | 8000 | 对外 REST API，提供 `/health`、`/generate`、`/metrics` |
| vLLM | 8002 | OpenAI-compatible inference server，提供 `/v1/models`、`/v1/chat/completions`、`/metrics` |
| vLLM worker / internal | 8003 | vLLM distributed worker/internal communication |

## 3. 已接入的 Metrics

### 3.1 FastAPI Metrics

FastAPI 已接入 Prometheus metrics，主要指标包括：

| Metric | Meaning |
|---|---|
| `http_requests_total` | 请求总数，按 method/status/handler 聚合 |
| `http_request_duration_highr_seconds_bucket` | 请求延迟 histogram，可用于计算 P50/P95 |
| `http_request_size_bytes` | 请求体大小 |
| `http_response_size_bytes` | 响应体大小 |
| `process_resident_memory_bytes` | FastAPI 进程内存占用 |
| `process_cpu_seconds_total` | FastAPI 进程 CPU 使用时间 |

已保存 evidence：

| Evidence | Path |
|---|---|
| FastAPI 64K metrics head | `evidence/week2_64k_context/results/week2_fastapi_64k_metrics_head.txt` |
| FastAPI 64K health | `evidence/week2_64k_context/results/week2_fastapi_64k_health.json` |
| FastAPI 64K log | `evidence/week2_64k_context/logs/week2_fastapi_vllm_64k.log` |

### 3.2 vLLM Metrics

vLLM 已暴露 Prometheus metrics，主要指标包括：

| Metric | Meaning |
|---|---|
| `vllm:num_requests_running` | 当前正在执行的请求数 |
| `vllm:num_requests_waiting` | 当前排队等待的请求数 |
| `vllm:kv_cache_usage_perc` | KV cache 使用率 |
| `vllm:prefix_cache_queries_total` | Prefix cache 查询 token 数 |
| `vllm:prefix_cache_hits_total` | Prefix cache 命中 token 数 |
| `vllm:prompt_tokens_total` | 累计 prefill/prompt tokens |
| `vllm:generation_tokens_total` | 累计 generation tokens |
| `vllm:num_preemptions_total` | 请求被抢占次数 |

已保存 evidence：

| Evidence | Path |
|---|---|
| vLLM 64K metrics head | `evidence/week2_64k_context/results/week2_seed_oss_vllm_64k_metrics_head.txt` |
| vLLM 64K metrics after smoke | `evidence/week2_64k_context/results/week2_vllm_64k_metrics_snapshot_after_smoke.txt` |
| vLLM metrics after 16K | `evidence/week2_64k_context/results/week2_vllm_metrics_snapshot_after_context_16k_on_64k_service.txt` |
| vLLM metrics after 32K | `evidence/week2_64k_context/results/week2_vllm_metrics_snapshot_after_context_32k_on_64k_service.txt` |
| vLLM metrics after 64K conservative | `evidence/week2_64k_context/results/week2_vllm_metrics_snapshot_after_context_64k_conservative_on_64k_service.txt` |
| vLLM metrics after 64K near-limit | `evidence/week2_64k_context/results/week2_vllm_metrics_snapshot_after_context_64k_near_limit_on_64k_service.txt` |
| Prefix cache before repeat | `evidence/week2_64k_context/results/week2_vllm_metrics_before_context_repeat_investigation.txt` |
| Prefix cache after repeat | `evidence/week2_64k_context/results/week2_vllm_metrics_after_context_repeat_investigation.txt` |

## 4. GPU 资源监控

### 4.1 nvidia-smi Snapshot

实验过程中保存了多次 `nvidia-smi` snapshot，用于观察模型加载后、推理请求后、长上下文请求后的 GPU 显存与利用率。

关键观察：

| Scenario | GPU memory | GPU utilization | Observation |
|---|---:|---:|---|
| vLLM 64K startup after load | ~75.8GB / 80GB per GPU | idle 0% when no request | 模型与 KV cache 预分配后显存接近上限 |
| FastAPI/vLLM smoke request | ~75.8GB / 80GB per GPU | ~97–98% during inference | 两张 A100 都被 tensor parallel worker 使用 |
| 16K / 32K / 64K context requests | ~75.8GB / 80GB per GPU | ~98% during request | 长上下文请求会使 GPU 进入高利用率状态 |
| After request completion | ~75.8GB / 80GB per GPU | 0% when idle | 显存被 vLLM worker 持续占用，计算利用率随请求变化 |

已保存 evidence：

| Evidence | Path |
|---|---|
| GPU after 64K startup | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_vllm_64k_startup.txt` |
| GPU after 64K smoke | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_fastapi_64k_smoke.txt` |
| GPU after 16K context | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_context_16k_on_64k_service.txt` |
| GPU after 32K context | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_context_32k_on_64k_service.txt` |
| GPU after 64K conservative | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_context_64k_conservative_on_64k_service.txt` |
| GPU after 64K near-limit | `evidence/week2_64k_context/logs/week2_nvidia_smi_after_context_64k_near_limit_on_64k_service.txt` |

### 4.2 nvidia-smi Sampling

实验过程中还保存了连续采样 CSV：

| Evidence | Path |
|---|---|
| Week2 GPU sampling | `evidence/week2_64k_context/logs/week2_nvidia_smi_sampling_64k_context.csv` |
| Tail after 32K | `evidence/week2_64k_context/logs/week2_nvidia_smi_sampling_64k_context_tail_after_32k.txt` |
| Tail after 64K conservative | `evidence/week2_64k_context/logs/week2_nvidia_smi_sampling_64k_context_tail_after_64k_conservative.txt` |
| Tail after 64K near-limit | `evidence/week2_64k_context/logs/week2_nvidia_smi_sampling_64k_context_tail_after_64k_near_limit.txt` |

该采样用于观察长上下文请求期间 GPU utilization 和 memory usage 的变化。

## 5. Prometheus 配置

本项目已新增 Week2 Prometheus scrape 配置：

```text
deployment/monitoring/prometheus_week2.yml
```

该配置包含两个 scrape target：

| Job | Target | Purpose |
|---|---|---|
| `fastapi-inference-service` | `127.0.0.1:8000/metrics` | 采集 FastAPI 请求、延迟、进程状态 |
| `vllm-seed-oss` | `127.0.0.1:8002/metrics` | 采集 vLLM request queue、KV cache、prefix cache、token throughput |

配置文件：

```yaml
global:
  scrape_interval: 5s
  evaluation_interval: 5s

scrape_configs:
  - job_name: "fastapi-inference-service"
    metrics_path: "/metrics"
    static_configs:
      - targets:
          - "127.0.0.1:8000"
        labels:
          service: "fastapi"
          model: "ByteDance-Seed/Seed-OSS-36B-Instruct"

  - job_name: "vllm-seed-oss"
    metrics_path: "/metrics"
    static_configs:
      - targets:
          - "127.0.0.1:8002"
        labels:
          service: "vllm"
          model: "ByteDance-Seed/Seed-OSS-36B-Instruct"
```

## 6. Grafana Dashboard 配置

本项目已新增 Week2 Grafana dashboard JSON：

```text
deployment/monitoring/grafana_week2_seed_oss_dashboard.json
```

Dashboard 覆盖以下面板：

| Panel | Metric |
|---|---|
| FastAPI Request Rate | `sum(rate(http_requests_total[1m]))` |
| FastAPI P95 Latency | `histogram_quantile(0.95, sum(rate(http_request_duration_highr_seconds_bucket[1m])) by (le))` |
| vLLM Running / Waiting Requests | `vllm:num_requests_running`, `vllm:num_requests_waiting` |
| vLLM KV Cache Usage | `vllm:kv_cache_usage_perc` |
| vLLM Prefix Cache Queries / Hits | `rate(vllm:prefix_cache_queries_total[1m])`, `rate(vllm:prefix_cache_hits_total[1m])` |
| vLLM Prompt / Generation Tokens | `rate(vllm:prompt_tokens_total[1m])`, `rate(vllm:generation_tokens_total[1m])` |

当前 dashboard JSON 已通过 `python -m json.tool` 格式校验，并已保存一次 Grafana live load probe 截图作为实机导入与负载观测证据：`figures/week2/observability/week2_grafana_seed_oss_live_load_probe.png`。

## 7. 资源瓶颈分析

### 7.1 显存瓶颈

Seed-OSS-36B-Instruct 在 BF16、TP=2、`max_model_len=65536` 配置下，每张 A100 80GB 显存占用约 75.8GB。这说明当前环境下显存余量非常有限。

主要显存占用来源包括：

1. BF16 模型权重；
2. KV cache；
3. CUDA graph；
4. vLLM runtime overhead；
5. tensor parallel worker 运行开销。

当前 64K 服务启动日志显示：

```text
GPU KV cache size: 290,448 tokens
Maximum concurrency for 65,536 tokens per request: 4.43x
```

该结果说明当前资源可以支撑 64K 级别长上下文服务，但对于 512K 单请求仍缺少 KV cache token capacity。该问题已在 `docs/week2_512k_feasibility_and_resource_analysis.md` 中单独分析。

### 7.2 计算利用率

nvidia-smi snapshot 显示，在实际推理请求期间，两张 A100 的 GPU utilization 可达到约 97–98%。当请求完成后，GPU utilization 回到 0%，但显存仍被 vLLM worker 持续占用。

这说明：

1. 推理期间 GPU 计算资源被有效使用；
2. idle 阶段主要问题不是计算利用率，而是显存常驻占用；
3. 对在线 serving 来说，提高请求到达率、batching 效率和 prefix cache 命中率可以改善单位时间 GPU 使用效率；
4. 对长上下文场景，显存/KV cache 比单纯 GPU utilization 更接近瓶颈。

### 7.3 Prefix Cache 行为

Prefix cache repeat investigation 显示，重复长文本请求会显著影响 latency。复测后，56K 与 61.9K 请求 latency 均下降到约 4.2s 左右。

vLLM metrics after repeat investigation 显示：

```text
vllm:prefix_cache_queries_total = 526194
vllm:prefix_cache_hits_total = 464096
```

该结果说明：

1. 重复 prompt 场景下 prefix cache 命中显著；
2. cached prompt latency 不能代表 cold prompt 长上下文性能；
3. benchmark 必须区分 cold prompt、warm prompt 和 prefix-cache-hit prompt；
4. Prefix Cache 是长上下文 serving 的重要优化方向，但不能替代 cold prompt 资源评估。

## 8. 对 Week2 任务要求的回应

Week2 要求使用 Prometheus + Grafana 分析 GPU 利用率和内存瓶颈。当前阶段已完成：

1. FastAPI `/metrics` 接入；
2. vLLM `/metrics` 接入；
3. nvidia-smi snapshot 与 sampling CSV 保存；
4. vLLM KV cache、Prefix Cache、running/waiting requests 指标采集；
5. Prometheus scrape config；
6. Grafana dashboard JSON；
7. GPU 显存瓶颈、计算利用率和 Prefix Cache 行为分析。

当前阶段尚未完成：

1. 长时间运行的 Prometheus TSDB 数据保留；
2. 多节点/多实例下的统一 dashboard；
3. 告警规则与高负载场景联动验证。

上述内容作为后续高可用与运维可视化增强方向。

## 9. 后续工作

后续可观测性增强方向：

1. 在下一次 RunPod/GPU 窗口启动 Prometheus + Grafana；
2. 导入 `grafana_week2_seed_oss_dashboard.json`；
3. 在并发 benchmark 和长上下文 benchmark 期间截图保存 dashboard；
4. 增加 GPU exporter 或 DCGM exporter，以获得更完整的 GPU temperature、power、memory、SM utilization 指标；
5. 将 Grafana dashboard 与 Week3 高可用、多实例、降级策略测试结合；
6. 补充 alert rules，例如高 P95、高 error rate、高 waiting requests、高 KV cache usage。

## 10. 结论

当前项目已具备基础可观测性闭环：FastAPI metrics、vLLM metrics、GPU snapshot、GPU sampling、Prometheus 配置和 Grafana dashboard JSON。实验结果显示，Seed-OSS-36B-Instruct 在 2×A100 80GB BF16 TP=2 环境下的主要瓶颈是显存与 KV cache capacity，而不是单次请求期间的 GPU 计算利用率。

该结论为后续量化优化、FP8 KV Cache、动态 batching、长上下文扩展和高可用服务治理提供了监控基础。

---

## 11. Week2 最终 Metrics Evidence 补充

本节补充本轮最终完成的 GSM8K full benchmark、codegen mini eval 和 dynamic batching sweep 对应的可观测性 evidence。

### 11.1 新增监控快照

| 场景 | GPU snapshot | vLLM metrics | FastAPI metrics |
|---|---|---|---|
| GSM8K full benchmark | `logs/week2_nvidia_smi_after_gsm8k_full_budget0.txt` | `results/week2_vllm_metrics_after_gsm8k_full_budget0.txt` | `results/week2_fastapi_metrics_after_gsm8k_full_budget0.txt` |
| Codegen mini eval | `logs/week2_nvidia_smi_after_codegen_mini_budget0.txt` | `results/week2_vllm_metrics_after_codegen_mini_budget0.txt` | `results/week2_fastapi_metrics_after_codegen_mini_budget0.txt` |
| Dynamic batch sweep | `logs/week2_nvidia_smi_after_dynamic_batch_sweep.txt` | `results/week2_vllm_metrics_after_dynamic_batch_sweep.txt` | `results/week2_fastapi_metrics_after_dynamic_batch_sweep.txt` |

这些文件用于证明每轮关键实验之后都保存了 GPU、vLLM 和 FastAPI 层面的状态快照，避免只保留 benchmark CSV 而缺少系统侧证据。

### 11.2 GSM8K Full Benchmark 监控结论

GSM8K full benchmark 共完成 1319 个样本，所有请求均通过 FastAPI `/generate` 成功返回，API error rate 为 0。

关键性能结果：

| 指标 | 结果 |
|---|---:|
| Total cases | 1319 |
| API error rate | 0.0 |
| Accuracy | 75.74% |
| Client latency P50 | 5.51s |
| Client latency P95 | 6.69s |
| Average tokens/s | 38.30 |

该实验说明服务在长时间顺序推理任务中保持稳定。GPU snapshot 显示，在 benchmark 完成后 vLLM worker 仍常驻占用显存，但 GPU utilization 回到 idle 状态。这符合 vLLM serving 的常驻模型服务模式：显存长期占用，计算利用率随请求变化。

### 11.3 Codegen Mini Eval 监控结论

Codegen mini eval 共完成 5 个 Python 函数生成任务，全部 API 请求成功，简单正确性检查为 5/5 passed。

关键性能结果：

| 指标 | 结果 |
|---|---:|
| Total cases | 5 |
| API error rate | 0.0 |
| Simple correctness | 5 / 5 passed |
| Latency range | 0.505s – 1.627s |

该实验请求较短，因此 latency 明显低于 GSM8K full benchmark。它用于验证同一套 FastAPI + VLLMBackend + vLLM 服务链路可以支持代码生成场景，而不是只支持自然语言摘要或数学推理。

### 11.4 Dynamic Batch Sweep 监控结论

Dynamic batch sweep 完成 concurrency=1/2/4/8/16 的测试，每个并发级别发送 40 个请求。

关键性能结果：

| Concurrency | QPS | P95 latency (s) | Error rate | Avg tokens/s |
|---:|---:|---:|---:|---:|
| 1 | 0.325 | 3.348 | 0.0 | 38.294 |
| 2 | 0.659 | 3.320 | 0.0 | 38.586 |
| 4 | 1.238 | 3.361 | 0.0 | 38.302 |
| 8 | 2.368 | 3.400 | 0.0 | 37.868 |
| 16 | 3.848 | 3.532 | 0.0 | 36.602 |

该结果体现出 vLLM continuous batching 的系统行为：

1. QPS 从 0.325 提升到 3.848，吞吐提升约 11.84×；
2. P95 latency 从 3.348s 上升到 3.532s，仅增加约 5.5%；
3. error rate 始终为 0；
4. Avg tokens/s 小幅下降，说明高并发下单请求生成速率略有牺牲；
5. 整体服务吞吐收益远大于尾延迟损失。

### 11.5 对可观测性任务要求的回应

结合原有 64K 长上下文、Prefix Cache 复测，以及本轮新增 GSM8K/codegen/dynamic batch evidence，当前可观测性闭环包括：

1. FastAPI request / latency / process metrics；
2. vLLM running requests、waiting requests、KV cache、Prefix Cache、token throughput metrics；
3. nvidia-smi snapshot；
4. benchmark CSV summary；
5. 不同实验场景后的 metrics snapshot；
6. 原始 evidence package 归档。

当前仍未完成的是长时间 Prometheus TSDB 留存、多节点统一 dashboard 和告警规则验证。该部分作为后续高可用与运维可视化增强方向。
