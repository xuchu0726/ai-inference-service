# Week2 剩余 GPU 实验计划

## 1. 文档目的

本文档记录当前 Week2 性能优化阶段仍需补齐的 GPU 实验，用于完善推理服务的监控可视化、动态 batch 参数测试和精度配置可行性验证。

下一次 GPU 窗口应集中完成三类高优先级任务：

1. Grafana dashboard 实机截图；
2. `max_num_batched_tokens` 动态 batch 参数测试；
3. FP32 feasibility 启动测试。

这三项分别对应当前性能优化阶段中的三个缺口：

1. 监控可视化 evidence；
2. batch scheduling 参数级实验；
3. FP32 与 BF16 baseline 的资源可行性对比。

---

## 2. 下一次 GPU 窗口执行顺序

### 2.1 启动 Seed-OSS 推理服务

先启动已经验证过的 Seed-OSS-36B-Instruct serving 链路。

预期服务如下：

| 服务 | 端口 | 作用 |
|---|---:|---|
| vLLM | 8002 | OpenAI-compatible 推理服务 |
| FastAPI | 8000 | 对外 `/generate` API |
| Prometheus | 9090 | 采集 FastAPI / vLLM metrics |
| Grafana | 3000 | 展示 dashboard |

需要保存的证据：

| Evidence | Path |
|---|---|
| vLLM 启动日志 | `logs/week2_remaining_seed_oss_vllm.log` |
| FastAPI 启动日志 | `logs/week2_remaining_fastapi.log` |
| vLLM model metadata | `results/week2_remaining_vllm_models.json` |
| FastAPI health | `results/week2_remaining_fastapi_health.json` |
| 启动后的 nvidia-smi | `logs/week2_remaining_nvidia_smi_after_startup.txt` |

---

## 3. Grafana Dashboard 截图

### 3.1 实验目的

验证 Prometheus + Grafana 监控链路能够展示真实推理服务指标，而不仅仅是保存离线 metrics 文件。

### 3.2 需要保存的截图

| Screenshot | Path |
|---|---|
| Grafana dashboard 总览 | `figures/week2/observability/week2_grafana_dashboard_overview.png` |
| FastAPI 请求与延迟面板 | `figures/week2/observability/week2_grafana_fastapi_latency.png` |
| vLLM running / waiting requests 面板 | `figures/week2/observability/week2_grafana_vllm_queue.png` |
| vLLM KV cache / Prefix cache 面板 | `figures/week2/observability/week2_grafana_kv_prefix_cache.png` |

### 3.3 预期结论

该实验用于补齐当前服务的监控可视化证据。完成后，项目可以展示：

1. FastAPI API 层请求监控；
2. vLLM 推理引擎层队列和缓存监控；
3. GPU 显存与利用率证据；
4. dashboard 可视化展示能力。

---

## 4. max_num_batched_tokens 参数测试

### 4.1 实验目的

当前项目已经完成 concurrency=1/2/4/8/16 的并发测试，但该实验主要评估请求侧压力变化。

为了进一步分析 vLLM 的 batch scheduling 行为，需要补充 `max_num_batched_tokens` 参数测试。该参数会影响单次调度允许处理的 token 数，从而影响吞吐、延迟和显存压力。

### 4.2 计划测试矩阵

| max_num_batched_tokens | concurrency | max_new_tokens | thinking_budget |
|---:|---:|---:|---:|
| 4096 | 8 | 128 | 0 |
| 8192 | 8 | 128 | 0 |
| 16384 | 8 | 128 | 0 |
| 32768 | 8 | 128 | 0 |

### 4.3 需要记录的指标

每组实验需要记录：

1. QPS；
2. P50 latency；
3. P95 latency；
4. tokens/s；
5. error_rate；
6. GPU memory；
7. vLLM running requests；
8. vLLM waiting requests；
9. KV cache usage。

### 4.4 预期分析方向

该实验用于回答：

1. 更大的 `max_num_batched_tokens` 是否提高吞吐；
2. 是否带来更高 P95 latency；
3. 是否增加显存压力；
4. 在当前 Seed-OSS-36B-Instruct + 2×A100 80GB 配置下，哪个 batch 参数更稳定。

---

## 5. FP32 Feasibility 启动测试

### 5.1 实验目的

当前项目已经完成 BF16 baseline，但尚未完成 FP32 实机可行性验证。

由于 Seed-OSS-36B-Instruct 的 FP32 权重显存需求显著高于 BF16，该实验不以成功启动为唯一目标。若启动失败，也需要保存清晰的资源边界证据。

### 5.2 需要保存的证据

| Evidence | Path |
|---|---|
| FP32 启动日志 | `logs/week2_fp32_feasibility_startup.log` |
| FP32 尝试前 nvidia-smi | `logs/week2_fp32_nvidia_smi_before.txt` |
| FP32 尝试后 nvidia-smi | `logs/week2_fp32_nvidia_smi_after.txt` |
| FP32 结果说明 | `docs/week2_fp32_feasibility_result.md` |

### 5.3 成功或失败的解释方式

如果 FP32 启动成功，应继续记录：

1. GPU memory；
2. P50 / P95 latency；
3. tokens/s；
4. error_rate；
5. 与 BF16 baseline 的对比。

如果 FP32 启动失败，应记录：

1. 是否 OOM；
2. 是否 vLLM 不支持；
3. 是否 CUDA / torch / kernel 不兼容；
4. 当前 2×A100 80GB 是否缺少显存余量；
5. 为什么 BF16 是当前可运行 baseline。

---

## 6. 停止规则

下一次 GPU 窗口完成后，必须先保存以下内容，再停止 GPU：

1. benchmark CSV；
2. summary CSV；
3. vLLM metrics；
4. FastAPI metrics；
5. nvidia-smi snapshot；
6. Grafana screenshots；
7. startup logs；
8. failure logs；
9. artifact tarball；
10. git status 和文件清单。

只有这些证据都保存后，才可以停止 GPU。
