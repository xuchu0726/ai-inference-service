# Grafana Dashboard 设计说明

## 1. 文档目的

本文档说明 Week2 性能优化阶段的 Grafana 监控面板设计，用于观察 FastAPI、vLLM 和 GPU 推理服务在并发、长上下文和不同推理预算下的性能变化。

Week1 已经完成：

1. vLLM `/metrics` 验证；
2. FastAPI `/metrics` 接入；
3. Prometheus 指标基础输出；
4. P50/P95、tokens/s、error_rate 的 benchmark 统计。

Week2 目标是在此基础上补充 Prometheus + Grafana 监控视图，用于分析：

1. 请求量；
2. 请求延迟；
3. 错误率；
4. vLLM running / waiting requests；
5. KV Cache 使用率；
6. prefix cache 命中情况；
7. GPU 显存和利用率；
8. 并发和上下文长度变化下的瓶颈。

---

## 2. 监控对象

当前推理服务链路：

    Client
    -> FastAPI /generate
    -> VLLMBackend
    -> vLLM OpenAI-compatible Server
    -> Seed-OSS-36B-Instruct
    -> GPU inference

监控对象分为三层：

| 层级 | 服务 | 说明 |
|---|---|---|
| API 层 | FastAPI | 观察 HTTP 请求、延迟、错误率 |
| 推理引擎层 | vLLM | 观察队列、KV Cache、prefix cache、请求状态 |
| GPU 层 | NVIDIA GPU | 观察显存、利用率、OOM 风险 |

---

## 3. Prometheus Scrape 配置

配置文件：

    deployment/monitoring/prometheus.yml

当前设计包含两个 scrape job：

1. FastAPI service:

        http://<host>:8000/metrics

2. vLLM server:

        http://<host>:8002/metrics

注意：

在 Docker Compose 或本地容器环境中，可以使用 `host.docker.internal` 访问宿主机端口；在 Linux server 环境中，可能需要改为实际 IP 或 `127.0.0.1`。

---

## 4. FastAPI Dashboard Panels

### 4.1 请求总量

指标：

    http_requests_total

用途：

观察 `/generate` 请求量是否随 benchmark concurrency 增加而增加。

### 4.2 请求延迟

指标：

    http_request_duration_seconds_count
    http_request_duration_seconds_sum
    http_request_duration_seconds_bucket

用途：

观察 API 层 latency，以及是否出现尾延迟增长。

### 4.3 状态码分布

指标：

    http_requests_total{status=~"2xx|4xx|5xx"}

用途：

观察错误率，区分正常请求、参数错误和服务异常。

### 4.4 请求大小与响应大小

指标：

    http_request_size_bytes
    http_response_size_bytes

用途：

分析长上下文输入和长输出对服务开销的影响。

---

## 5. vLLM Dashboard Panels

### 5.1 Running Requests

指标：

    vllm:num_requests_running

用途：

观察当前正在执行推理的请求数量。

### 5.2 Waiting Requests

指标：

    vllm:num_requests_waiting

用途：

观察请求是否在 vLLM 队列中排队。并发增加后，如果 waiting requests 增加，说明服务进入排队瓶颈。

### 5.3 KV Cache Usage

指标：

    vllm:kv_cache_usage_perc

用途：

分析长上下文和高并发下 KV Cache 是否接近上限，是判断 OOM 风险的重要指标。

### 5.4 Prefix Cache Queries / Hits

指标：

    vllm:prefix_cache_queries_total
    vllm:prefix_cache_hits_total

用途：

观察 prefix cache 是否对重复 prompt 或相似上下文产生缓存收益。

---

## 6. GPU Monitoring 设计

如果环境支持 DCGM Exporter 或 NVML exporter，可以将 GPU 指标接入 Prometheus。

优先关注：

1. GPU memory used；
2. GPU utilization；
3. GPU power usage；
4. GPU temperature；
5. GPU memory utilization；
6. OOM / Xid error。

如果当前环境暂未接入 GPU exporter，则使用 `nvidia-smi` 定时采样作为替代：

    nvidia-smi --query-gpu=timestamp,index,name,memory.used,memory.total,utilization.gpu,utilization.memory --format=csv -l 5

输出保存到：

    logs/week2_nvidia_smi_sampling.csv

---

## 7. Week2 推荐图表

Grafana 或离线 matplotlib 图表应至少覆盖：

1. QPS vs concurrency；
2. P95 latency vs concurrency；
3. tokens/s vs concurrency；
4. GPU memory vs context length；
5. KV Cache usage vs context length；
6. error_rate vs concurrency；
7. running/waiting requests vs concurrency。

---

## 8. 与 Week2 任务要求的对应关系

| Week2 要求 | 本文档对应内容 |
|---|---|
| Prometheus + Grafana 分析 GPU 利用率、内存瓶颈 | 设计 FastAPI/vLLM/GPU 三层监控 |
| 动态 Batch 调度分析 | 通过 running/waiting requests 与并发测试观察排队和 batching 行为 |
| KV Cache 优化 | 通过 kv_cache_usage_perc 观察上下文和并发下的 KV Cache 压力 |
| 图表展示 QPS、延迟、P95 | 指定 QPS/P95/tokens/s/error_rate 图表 |
| 性能优化报告 | 作为 Week2 报告的监控章节依据 |

---

## 9. 当前状态与后续计划

当前状态：

1. FastAPI `/metrics` 已接入；
2. vLLM `/metrics` 已验证；
3. Prometheus scrape 配置已准备；
4. Grafana dashboard 设计已完成文档化。

后续计划：

1. 在 GPU 实验环境中启动 Prometheus；
2. 配置 Grafana datasource；
3. 在 concurrency 和 context length benchmark 期间采集指标；
4. 保存 dashboard 截图或导出 JSON；
5. 将监控观察写入 `docs/week2_performance_optimization_report.md`。
