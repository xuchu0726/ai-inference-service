# 第 1 周交付报告：Seed-OSS-36B 基础集成、推理服务封装与性能验证

## 1. 交付概述

第 1 周围绕 Seed-OSS-36B-Instruct 的基础集成、服务化封装、推理预算控制、基础监控和初步性能验证展开。当前已完成从 FastAPI RESTful API、VLLMBackend、vLLM OpenAI-compatible Server 到 Seed-OSS-36B-Instruct GPU 推理的端到端链路。

本周核心交付结果包括：

1. 完成 Seed-OSS-36B-Instruct 在 2×NVIDIA A100-SXM4-80GB GPU 环境下的模型加载与推理验证。
2. 使用 vLLM 0.11.2 启动 Seed-OSS-36B-Instruct OpenAI-compatible 推理服务。
3. 使用 Tensor Parallel Size = 2 完成 36B 模型双卡部署。
4. 基于 FastAPI 封装 `/health`、`/generate` 和 `/metrics` 接口。
5. 实现 FastAPI 到 vLLM `/v1/chat/completions` 的后端调用链路。
6. 接入 Thinking Budget 参数，并验证 `thinking_budget=512` 与 `thinking_budget=1024` 两组配置。
7. 完成长文本法律摘要场景验证。
8. 完成 vLLM 与 FastAPI 两层 Prometheus 基础指标暴露。
9. 完成顺序请求、不同预算对比、concurrency=2、concurrency=4 的初步性能测试。
10. 记录并处理依赖安装、端口冲突、服务 readiness、FastAPI metrics 接入和文件系统 I/O 等问题。
11. 保存模型启动日志、服务日志、benchmark CSV、OpenAPI schema、metrics 输出和 GPU 状态证据。
12. 将代码变更与运行证据提交到代码仓库。

本周形成的核心调用链路如下：

    Client
      -> FastAPI /generate
      -> VLLMBackend
      -> vLLM OpenAI-compatible Server
      -> Seed-OSS-36B-Instruct
      -> 2×NVIDIA A100-SXM4-80GB GPU inference

相关代码和证据提交：

    576af80 启用 FastAPI Prometheus 指标暴露
    6fdbff8 补充 Seed-OSS Week1 运行证据与性能结果

---

## 2. 与第 1 周任务要求的对应关系

| 第 1 周任务要求 | 本周完成情况 | 证据或说明 |
|---|---|---|
| 封装推理逻辑为 RESTful API | 已完成 | FastAPI 已提供 `/health`、`/generate`、`/metrics` |
| 使用 FastAPI | 已完成 | 服务入口位于 `app/main.py` |
| 支持 Seed-OSS 基础集成 | 已完成 | Seed-OSS-36B-Instruct 已通过 vLLM 加载并完成 E2E 推理 |
| 支持 Seed-OSS 原生 512K 超长上下文能力 | 部分完成 | 本周使用 `max_model_len=4096` 完成稳定部署与链路验证；512K full-context 尚未实测 |
| 集成 Thinking Budget | 已完成 | 已完成 `thinking_budget=512/1024` 参数链路验证 |
| 动态调整推理深度 | 已完成基础参数链路 | API 层已支持传入不同 `thinking_budget`；后续需扩展更复杂任务评估推理深度差异 |
| 测试长文本处理 | 已完成基础验证 | 已完成法律文本摘要场景，input_tokens=379，output_tokens=256 |
| 验证 Seed-OSS 长上下文性能 | 部分完成 | 已完成中等长度业务文本验证；512K 长上下文性能需后续专项测试 |
| 错误日志记录 | 已完成 | 已记录依赖安装、端口冲突、metrics 接入、I/O 异常等问题 |
| 基础 Prometheus 接入 | 已完成 | vLLM `/metrics` 与 FastAPI `/metrics` 均已验证 |
| API 接口文档 | 已完成基础输出 | 已保存 FastAPI OpenAPI schema |
| 环境配置指南 | 已完成基础记录 | 已保存环境、依赖、服务启动和模型加载日志 |
| 初步性能测试报告 | 已完成 | 已完成 sequential、budget compare、concurrency=2、concurrency=4 测试 |
| GQA 注意力机制说明 | 已完成 | 本报告第 10 节包含 GQA 与 KV Cache 说明 |
| 推理预算控制代码示例 | 已完成 | 本报告第 6 节包含 Thinking Budget 请求结构 |
| 记录并解决模型加载、依赖冲突等环境问题 | 已完成 | 本报告第 11 节记录问题与处理过程 |

结论：第 1 周核心交付要求已完成。当前不足主要集中在 512K full-context 实测、质量评估体系、streaming/TTFT 指标和更高并发压测，后续继续优化与专项验证。

---

## 3. 系统架构与调用链路

### 3.1 整体架构

本周完成的系统采用 API 层与推理引擎层解耦的结构。FastAPI 负责对外暴露统一 RESTful API，vLLM 负责模型加载、GPU 调度、KV Cache 管理和实际推理执行。

完整调用链路如下：

    Client
      |
      | HTTP POST /generate
      v
    FastAPI Service
      |
      | app.main.generate()
      v
    app.inference.generate_text()
      |
      | VLLMBackend
      v
    vLLM OpenAI-compatible Server
      |
      | /v1/chat/completions
      v
    Seed-OSS-36B-Instruct
      |
      v
    GPU inference on 2×NVIDIA A100-SXM4-80GB

该结构将业务 API 与推理引擎分离。FastAPI 进程不直接加载 36B 模型，而是通过 VLLMBackend 调用独立 vLLM 服务。这种结构更接近真实推理服务架构，便于后续扩展监控、压测、负载均衡和多模型后端。

### 3.2 服务端口

本周验证过程中使用的主要服务端口如下：

| 服务 | 端口 | 作用 |
|---|---:|---|
| FastAPI service | 8000 | 对外业务 API，提供 `/health`、`/generate`、`/metrics` |
| vLLM server | 8002 | OpenAI-compatible 推理服务，提供 `/v1/models`、`/v1/chat/completions`、`/metrics` |
| vLLM worker distributed port | 8003 | vLLM worker 通信端口 |

初始部署时发现 8001 端口已被 nginx 占用，因此将 vLLM 服务端口调整为 8002，并在 FastAPI 侧设置：

    VLLM_BASE_URL=http://127.0.0.1:8002/v1

处理后，vLLM 与 FastAPI 均正常启动，服务链路可用。

---

## 4. 环境与模型部署

### 4.1 硬件与软件环境

本周 Seed-OSS-36B-Instruct 验证环境如下：

| 项目 | 配置 |
|---|---|
| GPU | 2×NVIDIA A100-SXM4-80GB |
| Python | 3.11.10 |
| vLLM | 0.11.2 |
| PyTorch | 2.9.0+cu128 |
| Transformers | 4.57.6 |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理精度 | bfloat16 |
| Tensor Parallel Size | 2 |
| max_model_len | 4096 |
| max_num_batched_tokens | 8192 |
| gpu_memory_utilization | 0.90 |

环境检查显示，两张 A100-SXM4-80GB GPU 均可见，CUDA 可用，vLLM、PyTorch 和 Transformers 环境均可正常使用。

### 4.2 vLLM 启动参数

Seed-OSS-36B-Instruct 使用双卡 Tensor Parallel 启动，核心配置如下：

    VLLM_PORT=8002
    TENSOR_PARALLEL_SIZE=2
    MAX_MODEL_LEN=4096
    MAX_NUM_BATCHED_TOKENS=8192
    GPU_MEMORY_UTILIZATION=0.90
    DTYPE=bfloat16

vLLM 启动后，`/v1/models` 接口返回可用模型：

    ByteDance-Seed/Seed-OSS-36B-Instruct

### 4.3 模型加载结果

模型加载阶段记录到的关键结果如下：

| 指标 | 结果 |
|---|---:|
| 模型权重缓存占用 | 约 68GB |
| safetensors shard 数量 | 15 |
| 权重下载耗时 | 约 590s |
| 权重加载耗时 | 约 59s |
| 初始模型加载显存 | 约 33.86 GiB / TP worker |
| GPU KV Cache capacity | 290,448 tokens |
| 4096 tokens/request 最大并发估计 | 约 70.91x |
| 稳定运行时 GPU 显存 | 约 75.8GB / 80GB per GPU |

稳定运行阶段的 GPU 显存记录如下：

    GPU 0: approximately 75797 MiB / 81920 MiB
    GPU 1: approximately 75797 MiB / 81920 MiB

该结果说明，在 BF16、TP=2、max_model_len=4096 的配置下，Seed-OSS-36B-Instruct 可以完成加载和基础推理。由于稳定运行时显存占用接近 76GB/80GB，后续进行更长上下文、更大 batch 或更高并发测试时，需要重点关注 KV Cache 增长与 OOM 风险。

### 4.4 服务启动顺序

本周验证采用以下启动顺序：

1. 激活 Python virtual environment；
2. 启动 vLLM OpenAI-compatible server；
3. 通过 `/v1/models` 验证 vLLM readiness；
4. 设置 FastAPI 环境变量，包括 `VLLM_BASE_URL`、`MODEL_NAME`、`VLLM_MODEL_NAME` 和 `VLLM_ENABLE_SEED_THINKING_BUDGET`；
5. 启动 FastAPI service；
6. 调用 `/health` 验证 API 服务状态；
7. 调用 `/generate` 完成端到端推理；
8. 调用 vLLM `/metrics` 与 FastAPI `/metrics` 验证基础监控指标。

该启动顺序避免了 FastAPI 已启动但下游 vLLM 尚未 ready 导致的连接失败问题。

---

## 5. FastAPI RESTful API 封装

### 5.1 已实现接口

本周完成 FastAPI 服务封装，核心接口如下：

| Endpoint | Method | 功能 |
|---|---|---|
| `/health` | GET | 健康检查 |
| `/generate` | POST | 文本生成推理 |
| `/metrics` | GET | Prometheus 指标暴露 |

### 5.2 `/generate` 请求格式

`/generate` 接口支持以下字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| prompt | string | 用户输入文本 |
| max_new_tokens | integer | 最大生成 token 数 |
| temperature | float | 采样温度 |
| thinking_budget | integer or null | Seed-OSS 推理预算参数 |

示例请求：

    {
      "prompt": "请用三句话解释什么是大模型推理服务。",
      "max_new_tokens": 128,
      "temperature": 0.7,
      "thinking_budget": 512
    }

### 5.3 `/generate` 响应格式

接口返回结果包含模型输出、延迟、token 统计、后端信息和模型信息。示例字段如下：

    {
      "response": "...",
      "latency_seconds": 3.361803,
      "input_chars": 36,
      "max_new_tokens": 128,
      "thinking_budget": 512,
      "backend": "vllm",
      "input_tokens": 118,
      "output_tokens": 128,
      "tokens_per_second": 38.0748,
      "model_name": "ByteDance-Seed/Seed-OSS-36B-Instruct",
      "device": "vllm_server"
    }

### 5.4 FastAPI 与 vLLM 的连接配置

FastAPI 通过以下环境变量连接 vLLM 后端：

    MODEL_NAME=ByteDance-Seed/Seed-OSS-36B-Instruct
    VLLM_MODEL_NAME=ByteDance-Seed/Seed-OSS-36B-Instruct
    VLLM_BASE_URL=http://127.0.0.1:8002/v1
    VLLM_ENABLE_SEED_THINKING_BUDGET=true
    VLLM_TIMEOUT_SECONDS=600

该配置使 FastAPI 层可以通过 VLLMBackend 调用 vLLM OpenAI-compatible API，避免在 FastAPI 进程内直接加载大模型。

### 5.5 API 文档说明

本周已通过 FastAPI 自动生成 OpenAPI schema，并保存接口文档证据：

    results/seed_oss_fastapi_openapi.json

当前业务 API 包含 `/health`、`/generate` 和 `/metrics`。其中 `/generate` 是核心推理接口，支持 prompt、max_new_tokens、temperature 和 thinking_budget 等参数，并返回 response、latency_seconds、input_tokens、output_tokens、tokens_per_second、backend、model_name 和 device 等字段。

该 OpenAPI schema 可作为后续接口联调、前端/测试调用和自动化 API 文档生成的基础。

---

## 6. Thinking Budget 推理预算控制

### 6.1 参数传递链路

本周实现了 Thinking Budget 参数从 FastAPI 请求到 vLLM 请求体的透传。参数链路如下：

    HTTP request thinking_budget
      -> GenerateRequest.thinking_budget
      -> app.inference.generate_text()
      -> VLLMBackend.generate()
      -> vLLM chat_template_kwargs.thinking_budget
      -> Seed-OSS response

VLLMBackend 将 Thinking Budget 写入 vLLM 请求中的 `chat_template_kwargs`：

    {
      "model": "ByteDance-Seed/Seed-OSS-36B-Instruct",
      "messages": [
        {
          "role": "user",
          "content": "请用三句话解释什么是大模型推理服务。"
        }
      ],
      "max_tokens": 128,
      "temperature": 0.7,
      "chat_template_kwargs": {
        "thinking_budget": 512
      }
    }

### 6.2 验证结果

本周验证了两组推理预算：

| thinking_budget | 请求数 | 结果 |
|---:|---:|---|
| 512 | 已验证 | 请求成功，模型返回 `<seed:think>` 与 `<seed:cot_budget_reflect>` |
| 1024 | 已验证 | 请求成功，模型返回正常 |

Seed-OSS 输出中出现以下字段：

    <seed:think>
    <seed:cot_budget_reflect>

该结果说明 Thinking Budget 参数已进入模型响应链路。

### 6.3 响应时间对比

在本周预算对比测试中，`thinking_budget=512` 与 `thinking_budget=1024` 均成功完成请求。由于 `max_new_tokens` 固定为 128，输出长度受限，因此两组预算在端到端延迟上的差异不明显。

预算对比测试整体结果如下：

| 指标 | 数值 |
|---|---:|
| total_requests | 16 |
| successful_requests | 16 |
| failed_requests | 0 |
| error_rate | 0.0 |
| client_latency_avg | 3.349s |
| client_latency_p50 | 3.348s |
| client_latency_p95 | 3.357s |
| tokens_per_second_avg | 38.23 |

### 6.4 生成质量观察

本周不同 Thinking Budget 的生成质量对比以功能性观察为主。测试覆盖中文解释、法律文本摘要、KV Cache 解释和部署规划类 prompt。`thinking_budget=512` 与 `thinking_budget=1024` 均能触发 Seed-OSS thinking 输出，并返回与任务相关的内容。

由于本周 benchmark 中 `max_new_tokens=128`，部分回答会在较短输出长度下被截断，因此当前阶段不对 512 与 1024 的生成质量差异做强结论。更严格的质量对比需要使用更长输出、更复杂推理任务和结构化评分方式。

---

## 7. Prometheus 基础监控接入

### 7.1 vLLM metrics

vLLM 原生暴露 `/metrics` 接口。本周已验证以下关键指标：

    vllm:num_requests_running
    vllm:num_requests_waiting
    vllm:kv_cache_usage_perc
    vllm:prefix_cache_queries_total
    vllm:prefix_cache_hits_total

这些指标可用于分析：

1. 当前正在执行的请求数量；
2. 等待队列中的请求数量；
3. KV Cache 使用率；
4. Prefix cache 查询次数；
5. Prefix cache 命中情况。

### 7.2 FastAPI metrics

初始版本 FastAPI `/metrics` 返回 404。随后接入 `prometheus-fastapi-instrumentator`，并在 `app/main.py` 中添加：

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)

接入后，FastAPI `/metrics` 成功返回 HTTP 层指标，包括：

    http_requests_total{handler="/generate",method="POST",status="2xx"}
    http_request_duration_seconds_count{handler="/generate",method="POST"}
    http_request_duration_seconds_sum{handler="/generate",method="POST"}
    http_request_size_bytes_count{handler="/generate"}
    http_response_size_bytes_count{handler="/generate"}

该结果说明系统已具备基础 API 级别可观测性，可作为后续错误率统计、P95 延迟统计、请求量统计和服务容量分析的基础。

---

## 8. 功能验证

### 8.1 vLLM 模型服务验证

通过 vLLM `/v1/models` 接口验证模型服务可用，返回模型为：

    ByteDance-Seed/Seed-OSS-36B-Instruct

该结果说明模型已成功加载，并可通过 OpenAI-compatible API 访问。

### 8.2 vLLM chat completion 验证

直接调用 vLLM `/v1/chat/completions` 成功返回 Seed-OSS 输出，响应内容包含 `<seed:think>` 与 `<seed:cot_budget_reflect>` 字段，说明 Seed-OSS 模板与 Thinking Budget 参数链路生效。

### 8.3 FastAPI E2E 验证

通过 FastAPI `/generate` 完成端到端验证，结果如下：

| 指标 | 结果 |
|---|---:|
| HTTP status | 200 |
| client_latency_seconds | 约 3.37s |
| server latency_seconds | 约 3.36s |
| input_chars | 36 |
| input_tokens | 118 |
| output_tokens | 128 |
| tokens_per_second | 约 38.07 |
| backend | vllm |
| model_name | ByteDance-Seed/Seed-OSS-36B-Instruct |
| device | vllm_server |

该结果说明 FastAPI、VLLMBackend、vLLM server 和 Seed-OSS-36B-Instruct GPU 推理链路已经跑通。

### 8.4 长文本法律摘要验证

本周完成法律文本摘要场景验证。测试任务要求模型按“价格风险、解除风险、责任风险、数据风险、合规风险”对合同条款进行分类总结。

测试结果如下：

| 指标 | 结果 |
|---|---:|
| input_chars | 495 |
| input_tokens | 379 |
| max_new_tokens | 256 |
| thinking_budget | 512 |
| latency_seconds | 约 6.77s |
| output_tokens | 256 |
| tokens_per_second | 约 37.81 |
| backend | vllm |
| model_name | ByteDance-Seed/Seed-OSS-36B-Instruct |

该测试验证了服务对较长中文业务文本的处理能力，并能返回结构化风险分析内容。

需要说明的是，本周长文本验证尚未覆盖 512K full-context 输入。本周部署配置为 `max_model_len=4096`，主要用于完成模型加载、服务链路、预算控制、监控和性能基线验证。Seed-OSS 的更长上下文能力需要结合 KV Cache 显存占用、prefill latency、分块策略、并发退化和 OOM 边界进行专项验证。

---

## 9. 初步性能测试结果

### 9.1 顺序请求基线测试

测试配置：

| 参数 | 值 |
|---|---:|
| concurrency | 1 |
| thinking_budget | 512 |
| max_new_tokens | 128 |
| total_requests | 12 |

测试结果：

| 指标 | 数值 |
|---|---:|
| successful_requests | 12 |
| failed_requests | 0 |
| error_rate | 0.0 |
| client_latency_avg | 3.350s |
| client_latency_p50 | 3.348s |
| client_latency_p95 | 3.358s |
| tokens_per_second_avg | 38.23 |
| tokens_per_second_p50 | 38.25 |
| tokens_per_second_p95 | 38.27 |

### 9.2 Thinking Budget 对比测试

测试配置：

| 参数 | 值 |
|---|---:|
| concurrency | 1 |
| thinking_budgets | 512, 1024 |
| max_new_tokens | 128 |
| total_requests | 16 |

测试结果：

| 指标 | 数值 |
|---|---:|
| successful_requests | 16 |
| failed_requests | 0 |
| error_rate | 0.0 |
| client_latency_avg | 3.349s |
| client_latency_p50 | 3.348s |
| client_latency_p95 | 3.357s |
| tokens_per_second_avg | 38.23 |
| tokens_per_second_p50 | 38.24 |
| tokens_per_second_p95 | 38.28 |

观察结果：

1. 两组预算下请求均成功；
2. 在 `max_new_tokens=128` 的短输出场景中，512 与 1024 budget 的延迟差异不明显；
3. 模型输出均能进入 thinking 相关响应链路；
4. 当前测试不对不同预算下的质量差异做强结论。

### 9.3 concurrency=2 测试

测试配置：

| 参数 | 值 |
|---|---:|
| concurrency | 2 |
| thinking_budget | 512 |
| max_new_tokens | 128 |
| total_requests | 8 |

测试结果：

| 指标 | 数值 |
|---|---:|
| successful_requests | 8 |
| failed_requests | 0 |
| error_rate | 0.0 |
| client_latency_avg | 3.370s |
| client_latency_p50 | 3.370s |
| client_latency_p95 | 3.391s |
| tokens_per_second_avg | 38.02 |
| tokens_per_second_p50 | 38.00 |
| tokens_per_second_p95 | 38.20 |

### 9.4 concurrency=4 测试

测试配置：

| 参数 | 值 |
|---|---:|
| concurrency | 4 |
| thinking_budget | 512 |
| max_new_tokens | 128 |
| total_requests | 8 |

测试结果：

| 指标 | 数值 |
|---|---:|
| successful_requests | 8 |
| failed_requests | 0 |
| error_rate | 0.0 |
| client_latency_avg | 3.409s |
| client_latency_p50 | 3.404s |
| client_latency_p95 | 3.430s |
| tokens_per_second_avg | 37.59 |
| tokens_per_second_p50 | 37.65 |
| tokens_per_second_p95 | 37.68 |

### 9.5 性能结果小结

本周测试结果显示：

1. 在当前短输出场景下，服务顺序请求平均延迟约 3.35s；
2. concurrency 从 1 增加到 4 后，P95 latency 从约 3.36s 增加到约 3.43s；
3. 小并发测试下错误率保持 0%；
4. 输出吞吐稳定在约 37.6 至 38.2 tokens/s；
5. 当前 benchmark 为 non-streaming `/generate`，尚未统计 TTFT；
6. 更高并发、streaming、长上下文和 QPS 压测仍需后续扩展。

---

## 10. Seed-OSS GQA 与 KV Cache 说明

### 10.1 GQA 的作用

GQA，即 Grouped-Query Attention，是介于 MHA 和 MQA 之间的注意力结构。传统 Multi-Head Attention 中，每个 query head 通常对应独立的 key/value head；而 GQA 将多个 query head 共享一组 key/value head，从而减少 key/value 状态数量。

在推理阶段，尤其是长上下文和高并发场景中，KV Cache 会占用大量显存。GQA 可以减少 KV Cache 的规模，降低显存压力和内存带宽压力，使长上下文推理和多请求服务更容易维持稳定。

### 10.2 KV Cache 的工程意义

大语言模型自回归生成时，每生成一个 token 都需要访问历史 token 的 key/value 状态。如果不缓存这些状态，每一步都需要重复计算历史上下文，推理成本会显著增加。

KV Cache 的主要作用包括：

1. 减少重复计算；
2. 改善 decode 阶段延迟；
3. 支持长上下文推理；
4. 支持 continuous batching；
5. 帮助 vLLM 在多请求场景下管理显存与吞吐。

本周 vLLM 启动日志显示：

    GPU KV cache size: 290,448 tokens
    Maximum concurrency for 4,096 tokens per request: 70.91x

该结果说明当前配置下已具备可观的 KV Cache 容量，为后续长上下文扩展和并发优化提供基础。

---

## 11. 问题记录与处理

### 11.1 依赖版本变化

安装 vLLM 0.11.2 时，pip 自动替换部分依赖，包括 torch、triton、numpy、starlette 等。最终运行环境中关键版本如下：

    vLLM 0.11.2
    torch 2.9.0+cu128
    transformers 4.57.6

处理方式：

1. 使用独立 Python virtual environment 隔离依赖；
2. 保留完整安装日志；
3. 通过 import vLLM、vLLM CLI、PyTorch CUDA 检查和模型启动验证环境可用。

相关证据文件：

    logs/install_vllm.log

### 11.2 端口冲突

初始计划使用 8001 端口启动 vLLM，但该端口已被 nginx 占用。处理方式是将 vLLM 服务改为 8002：

    VLLM_PORT=8002
    VLLM_BASE_URL=http://127.0.0.1:8002/v1

处理结果：vLLM 成功启动，FastAPI 正确连接后端。

相关证据文件：

    logs/seed_oss_vllm_launch_port8002.log

### 11.3 FastAPI metrics 未启用

初始 FastAPI `/metrics` 返回 404。后续接入 `prometheus-fastapi-instrumentator`，并在 `app/main.py` 中加入：

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)

处理结果：FastAPI `/metrics` 成功暴露 HTTP 请求计数、响应耗时、请求大小和响应大小等指标。

相关提交：

    576af80 启用 FastAPI Prometheus 指标暴露

相关证据文件：

    results/seed_oss_fastapi_metrics_head_after_enable.txt
    results/seed_oss_fastapi_metrics_generate_head.txt
    logs/seed_oss_week1_metrics_final_evidence.txt

### 11.4 concurrency=4 CSV 写入异常

第一次 concurrency=4 测试中，请求均已返回 200，但写入 CSV 文件时出现一次：

    OSError: [Errno 5] Input/output error

处理方式：

1. 保留失败日志；
2. 将输出先写入临时路径；
3. 再保存成功版 retry CSV；
4. 将失败记录与成功结果一并纳入证据文件。

最终成功文件：

    results/seed_oss_fastapi_concurrency4_retry.csv
    logs/seed_oss_fastapi_concurrency4_retry.log
    logs/seed_oss_week1_final_plus_concurrency_evidence.txt

### 11.5 模型显存压力

Seed-OSS-36B-Instruct 在当前 BF16、TP=2、max_model_len=4096 配置下可以完成加载和推理，但稳定运行时每张 A100-SXM4-80GB 显存占用约 75.8GB。该结果说明当前配置可用于基础链路验证和短上下文/中等文本测试，但在更长上下文、更高并发或更大 batch 下存在 OOM 风险。

处理方式：

1. 本周先固定 `max_model_len=4096` 完成稳定部署基线；
2. 记录 KV Cache capacity 与最大并发估计；
3. 将更长上下文和更高并发作为后续专项验证内容。

---

## 12. 证据文件索引

本周运行证据已保存到 `logs/` 与 `results/` 目录，并提交到代码仓库。

### 12.1 环境与部署证据

    logs/install_vllm.log
    logs/seed_oss_vllm_launch_port8002.log
    results/seed_oss_vllm_models.json

### 12.2 FastAPI 与 E2E 证据

    logs/seed_oss_fastapi_launch.log
    logs/seed_oss_fastapi_launch_with_metrics.log
    results/seed_oss_fastapi_health.json
    results/seed_oss_fastapi_health_after_metrics.json
    results/seed_oss_fastapi_smoke_test.txt
    results/seed_oss_fastapi_smoke_test_after_metrics.txt

### 12.3 Prometheus 监控证据

    results/seed_oss_vllm_metrics_head.txt
    results/seed_oss_fastapi_metrics_head_after_enable.txt
    results/seed_oss_fastapi_metrics_generate_head.txt
    logs/seed_oss_week1_metrics_final_evidence.txt

### 12.4 性能测试证据

    results/seed_oss_fastapi_benchmark_3req.csv
    logs/seed_oss_fastapi_benchmark_3req.log
    results/seed_oss_fastapi_budget_compare.csv
    logs/seed_oss_fastapi_budget_compare.log
    results/seed_oss_fastapi_concurrency2.csv
    logs/seed_oss_fastapi_concurrency2.log
    results/seed_oss_fastapi_concurrency4_retry.csv
    logs/seed_oss_fastapi_concurrency4_retry.log
    logs/seed_oss_week1_final_plus_concurrency_evidence.txt

### 12.5 长文本场景证据

    results/seed_oss_long_legal_summary_512.json
    logs/seed_oss_after_long_legal_summary_nvidia_smi.txt

### 12.6 API 文档证据

    results/seed_oss_fastapi_openapi.json
    results/seed_oss_vllm_openapi_head.txt

### 12.7 汇总证据

    logs/seed_oss_e2e_success_evidence.txt
    logs/seed_oss_week1_final_inventory.txt
    logs/seed_oss_week1_metrics_final_evidence.txt
    logs/seed_oss_week1_final_plus_concurrency_evidence.txt

---

## 13. 当前未完全覆盖的内容与原因说明

本周已完成第 1 周任务中的主要工程闭环，但仍有部分内容尚未完全覆盖，具体如下。

### 13.1 512K full-context 尚未实测

任务要求中提到 Seed-OSS 的原生 512K 超长上下文能力。本周已经完成 Seed-OSS-36B-Instruct 的基础部署、API 链路、Thinking Budget、监控和性能基线验证，但当前部署配置为：

    max_model_len=4096

本周法律文本测试的输入规模为：

    input_tokens=379

因此，本周不能表述为已经完成 512K full-context 实测。当前完成的是 Seed-OSS 长上下文能力验证前的基础部署闭环和中等长度业务文本验证。512K full-context 验证涉及 KV Cache 显存增长、prefill latency、并发退化、分块策略和 OOM 边界，需要作为后续专项测试展开。

### 13.2 Thinking Budget 质量评估仍偏初步

本周已经验证 `thinking_budget=512` 与 `thinking_budget=1024` 均能正常进入模型响应链路，并完成响应时间对比。但由于本周 benchmark 的 `max_new_tokens=128`，部分输出会被截断，因此当前质量观察只能作为功能性验证，不能作为严格质量评估结论。

后续需要使用更长输出、更复杂任务和结构化评分方法，才能更准确评估不同 Thinking Budget 对推理深度、输出质量和延迟的影响。

### 13.3 当前 benchmark 尚未覆盖 streaming 与 TTFT

本周性能测试调用的是 non-streaming `/generate` API，已经统计端到端 latency、P50、P95、error rate 和 tokens/s。但尚未覆盖 streaming 输出，因此尚未统计 TTFT。

对于真实推理服务，TTFT 是用户体验和服务性能的重要指标，需要后续增加 streaming endpoint 或直接调用 vLLM streaming API 进行统计。

### 13.4 当前并发测试规模较小

本周完成了 concurrency=1、2、4 的初步测试，主要用于验证服务链路稳定性和小并发下的延迟变化。当前尚未覆盖 100/500/1000 QPS 档位压测，也尚未覆盖长文本、多模态和代码生成等复杂场景下的高并发压测。

### 13.5 当前监控为基础指标暴露

本周已经完成 vLLM `/metrics` 和 FastAPI `/metrics` 验证，但尚未搭建 Grafana dashboard，也尚未形成完整可视化监控面板。当前阶段已具备 Prometheus 指标采集基础，后续可以进一步扩展为 dashboard、告警规则和容量分析视图。

---

## 14. 本周总结

本周完成了 Seed-OSS-36B-Instruct 的基础部署、推理 API 封装、Thinking Budget 参数接入、Prometheus 基础监控、法律文本摘要验证和初步性能测试。系统已经形成从 HTTP 请求到 FastAPI、VLLMBackend、vLLM、Seed-OSS-36B-Instruct 和 GPU 推理的完整闭环。

在 2×NVIDIA A100-SXM4-80GB、bfloat16、Tensor Parallel Size=2、max_model_len=4096 配置下，Seed-OSS-36B-Instruct 能够稳定提供非流式文本生成服务。顺序请求、小并发测试和预算对比测试均达到 0% 错误率。短输出场景下，平均端到端延迟约 3.35s，输出吞吐约 38 tokens/s。

从工程角度看，本周已经完成以下基础：

1. 大模型服务化封装；
2. vLLM 后端接入；
3. Seed-OSS-36B 多卡加载；
4. Thinking Budget 参数链路；
5. Prometheus 基础可观测性；
6. 长文本业务场景验证；
7. 初步性能数据采集；
8. 环境问题和异常处理记录；
9. 可追溯的运行证据保存。

本周仍需后续深化的内容包括：512K full-context 专项测试、Thinking Budget 质量评估、streaming/TTFT 统计、更高并发压测、Grafana dashboard、量化优化和多模态/代码生成场景验证。