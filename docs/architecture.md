# 系统架构说明

## 1. 文档目的

本文档说明 AI Inference Service 当前的系统架构、模块职责、推理后端设计，以及后续迁移到 Seed-OSS-36B / Seed-Coder / BAGEL 的扩展路线。

本项目目标不是简单调用一个模型，而是构建一个可运行、可压测、可迁移的大模型推理服务系统。

当前系统已经完成从本地小模型验证到 CX3 GPU vLLM 推理服务验证的升级。

---

## 2. 项目目标

项目总目标：

    4 周内交付一个可运行的 AI 推理服务系统。

该系统应具备：

    1. RESTful API 服务
    2. 可插拔推理后端
    3. 真实模型推理能力
    4. GPU/vLLM serving 能力
    5. benchmark 性能统计
    6. 错误日志和故障记录
    7. 后续多卡部署和云 GPU 迁移能力
    8. 面向 Seed 系列模型的扩展路线

当前阶段重点是第 1 周任务：

    1. 环境搭建
    2. GPU 验证
    3. API 封装
    4. Thinking Budget 参数链路
    5. 基础推理验证
    6. 文档和问题记录

---

## 3. 当前整体架构

当前系统架构如下：

    Client
    → FastAPI API Layer
    → app.inference.generate_text()
    → InferenceBackend
    → MockBackend / TransformersBackend / VLLMBackend
    → Model Runtime
    → Structured API Response

当前已经实现三类后端：

    1. MockBackend
    2. TransformersBackend
    3. VLLMBackend

三类后端对应不同阶段：

    MockBackend:
        用于最早期 API 结构验证。

    TransformersBackend:
        用于本地真实模型推理验证。

    VLLMBackend:
        用于 GPU serving 和后续 Seed-OSS-36B 迁移。

---

## 4. FastAPI API 层

FastAPI 是当前系统的业务 API 层。

当前暴露接口：

    GET /health
    POST /generate

FastAPI 层负责：

    1. 接收 HTTP 请求
    2. 校验请求参数
    3. 拒绝空 prompt
    4. 接收 max_new_tokens、temperature、thinking_budget
    5. 调用 app.inference.generate_text()
    6. 返回统一 JSON response

FastAPI 层不直接负责模型加载和 GPU 推理。

这种设计的核心价值是：

    API 层稳定，推理后端可以替换。

后续从 Qwen 小模型切换到 Seed-OSS-36B 时，外部 API 不需要推倒重来。

---

## 5. app.inference 调度层

`app/inference.py` 是当前推理调度入口。

它根据环境变量选择后端：

    INFERENCE_BACKEND=mock
    INFERENCE_BACKEND=transformers
    INFERENCE_BACKEND=vllm

当前逻辑：

    1. 如果 INFERENCE_BACKEND == "mock"，使用 MockBackend
    2. 如果 INFERENCE_BACKEND == "transformers"，使用 TransformersBackend
    3. 如果 INFERENCE_BACKEND == "vllm"，使用 VLLMBackend
    4. 如果配置未知，则抛出错误

该层的作用是把 API 层和具体推理实现解耦。

---

## 6. InferenceBackend 抽象

项目定义了统一后端接口：

    generate(
        prompt: str,
        max_new_tokens: int,
        temperature: float,
        thinking_budget: int | None
    ) -> dict

统一接口的价值：

    1. 所有后端暴露同一 generate 方法
    2. FastAPI 不关心底层模型如何运行
    3. benchmark 脚本可以复用同一个 /generate 接口
    4. 后续可以增加新的推理引擎
    5. 后续可以增加 Seed-OSS、Seed-Coder、BAGEL 后端

该设计是项目从 单一脚本级模型调用示例 升级为工程化推理服务的关键。

---

## 7. MockBackend

MockBackend 是最早期后端。

作用：

    1. 快速验证 FastAPI 是否可运行
    2. 验证 /generate 接口格式
    3. 验证 thinking_budget 参数传递
    4. 验证 benchmark 脚本是否能请求服务
    5. 不依赖模型和 GPU

限制：

    1. 不是真实推理
    2. 不能代表性能
    3. 不能用于最终交付

MockBackend 的价值在于降低早期调试成本。

---

## 8. TransformersBackend

TransformersBackend 使用 Hugging Face Transformers 在本地进程内加载模型并推理。

当前已验证模型：

    Qwen/Qwen2.5-0.5B-Instruct

当前已验证环境：

    Apple M4
    24GB memory
    MPS
    PyTorch
    Transformers

已完成能力：

    1. 加载 tokenizer
    2. 加载 model
    3. 执行 model.generate()
    4. 解码输出
    5. 统计 input_tokens
    6. 统计 output_tokens
    7. 统计 latency_seconds
    8. 计算 tokens_per_second
    9. 返回 backend、model_name、device

该后端证明项目已经从 mock API 进入真实模型推理阶段。

限制：

    1. 不适合高并发
    2. 不支持 vLLM continuous batching
    3. 不适合生产级大模型 serving
    4. 不适合 Seed-OSS-36B

---

## 9. VLLMBackend

VLLMBackend 是当前最重要的工程升级。

它不在 FastAPI 进程内加载模型，而是调用独立的 vLLM OpenAI-compatible server。

当前链路：

    Client
    → FastAPI /generate
    → app.inference.generate_text()
    → VLLMBackend.generate()
    → vLLM /v1/chat/completions
    → GPU model
    → vLLM response
    → FastAPI response

VLLMBackend 负责：

    1. 构造 OpenAI-compatible chat completions 请求
    2. 将 max_new_tokens 映射为 max_tokens
    3. 传递 temperature
    4. 保留 thinking_budget 字段
    5. 请求 vLLM server
    6. 解析 response 文本
    7. 解析 input_tokens / output_tokens
    8. 计算 tokens_per_second
    9. 返回统一 response

这种设计更接近真实大模型服务架构。

---

## 10. vLLM 推理服务层

vLLM 负责底层 GPU 推理服务。

当前已验证 vLLM 环境：

    vLLM: 0.11.2
    torch: 2.9.0+cu128
    GPU: NVIDIA L40S
    Model: Qwen/Qwen2.5-1.5B-Instruct

vLLM 负责：

    1. 模型加载
    2. GPU 显存管理
    3. KV Cache 分配
    4. CUDA Graph
    5. prefix caching
    6. chunked prefill
    7. OpenAI-compatible API
    8. token usage 统计

当前 CX3 E2E 验证中，vLLM 暴露：

    GET /v1/models
    POST /v1/chat/completions
    GET /metrics

其中 `/v1/models` 被用于 readiness probe。

---

## 11. CX3 端到端验证架构

当前已经在 CX3 单卡 L40S 上跑通以下链路：

    Python test client
    → FastAPI /generate
    → VLLMBackend
    → vLLM /v1/chat/completions
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S GPU
    → API response

对应脚本：

    deployment/vllm/qwen_1_5b_vllm_fastapi_e2e.pbs

该脚本在 PBS 作业中完成：

    1. 申请 1 张 L40S GPU
    2. 激活 vLLM virtual environment
    3. 启动 vLLM server
    4. 轮询 /v1/models 等待 vLLM ready
    5. 启动 FastAPI server
    6. 请求 /health
    7. 请求 /generate
    8. 保存 response JSON
    9. 记录 nvidia-smi
    10. 停止服务并释放 GPU

该脚本同时承担：

    1. 部署脚本
    2. 服务启动脚本
    3. readiness 检查脚本
    4. E2E 测试客户端
    5. 结果记录脚本

这是 HPC/PBS 环境下合理的验证方式。

---

## 12. 当前已验证结果

CX3 E2E 验证结果：

    Job ID: 2700593.pbs-7
    GPU: NVIDIA L40S
    Model: Qwen/Qwen2.5-1.5B-Instruct
    vLLM readiness: /v1/models returned 200
    FastAPI /health: 200
    FastAPI /generate: 200
    client_latency_seconds: 2.408775
    server latency_seconds: 2.404936
    input_tokens: 50
    output_tokens: 128
    tokens_per_second: 53.2239
    GPU memory after request: 39819 MiB / 46068 MiB
    GPU utilization after request: 63%

该结果证明：

    1. FastAPI API 层可用
    2. VLLMBackend 适配层可用
    3. vLLM server 可用
    4. GPU 模型推理可用
    5. token usage 可解析
    6. tokens/s 可计算
    7. response JSON 可落盘

---

## 13. 当前监控与指标能力

当前系统已经具备基础指标返回能力：

    1. latency_seconds
    2. input_tokens
    3. output_tokens
    4. tokens_per_second
    5. backend
    6. model_name
    7. device
    8. status_code
    9. client_latency_seconds
    10. error_rate
    11. P50 latency
    12. P95 latency

当前已经完成本地 TransformersBackend benchmark，并生成：

    results/thinking_budget_benchmark.csv
    results/benchmark_summary.csv

后续需要把同样的 benchmark 流程接入 VLLMBackend，形成 vLLM benchmark 报告。

---

## 14. Thinking Budget 在架构中的位置

`thinking_budget` 当前作为 API 层参数进入系统：

    Request
    → FastAPI schema
    → generate_text()
    → backend.generate()
    → response / benchmark record

当前作用：

    1. 统一请求参数
    2. 支持实验分组
    3. 支持 benchmark 记录
    4. 为后续推理深度控制预留接口

当前限制：

    thinking_budget 尚未真正控制模型内部 reasoning tokens。

后续可能实现方式：

    1. 映射到 max_new_tokens
    2. 映射到 prompt-level 推理长度约束
    3. 映射到模型原生 reasoning budget 参数
    4. 映射到不同推理模式
    5. 对 latency / quality 做对比实验

---

## 15. Seed-OSS-36B 目标架构

后续 Seed-OSS-36B 部署目标架构：

    External client or benchmark tool
    → FastAPI service
    → VLLMBackend
    → vLLM server
    → Seed-OSS-36B
    → multi-GPU cloud instance

从当前 Qwen2.5-1.5B E2E 链路迁移到 Seed-OSS-36B 时，主要需要修改：

    1. VLLM_MODEL_NAME
    2. vLLM --model 参数
    3. tensor_parallel_size
    4. GPU 数量
    5. max_model_len
    6. gpu_memory_utilization
    7. dtype / quantization
    8. benchmark 参数

不需要推倒重来的部分：

    1. FastAPI /generate
    2. VLLMBackend
    3. benchmark 调用方式
    4. response schema
    5. 文档结构
    6. readiness probe 思路

---

## 16. 为什么当前设计已经具备工程化推理服务特征

单一脚本级模型调用示例通常是：

    直接在脚本里调用 model.generate(prompt)

当前项目已经具备：

    1. FastAPI RESTful API
    2. 可插拔后端抽象
    3. 本地 TransformersBackend
    4. GPU vLLMBackend
    5. vLLM OpenAI-compatible serving
    6. PBS 部署脚本
    7. readiness probe
    8. benchmark CSV
    9. P50 / P95 统计
    10. failure modes 记录
    11. Seed-OSS-36B 资源评估
    12. 云 GPU 迁移计划

因此当前项目已经是一个可扩展的大模型推理服务原型，而不是单文件模型调用 demo。

---

## 17. 当前限制

当前架构仍有以下限制：

    1. vLLM E2E 只完成单请求验证
    2. 尚未完成 vLLM 多请求 benchmark
    3. 尚未完成并发压测
    4. 尚未完成 Prometheus + Grafana 可观测性闭环
    5. 尚未部署 Seed-OSS-36B
    6. 尚未验证 512K 长上下文
    7. 尚未接入 BAGEL 多模态模型
    8. 尚未完成云 GPU 长时间服务部署

这些是后续 2-4 周需要推进的重点。

---

## 18. 下一步架构演进

下一步优先级：

    P0: 将 benchmark.py 扩展到 VLLMBackend
    P1: 生成 vLLM benchmark summary
    P2: 接入 Prometheus metrics
    P3: 增加并发压测脚本
    P4: 准备云 GPU Dockerfile
    P5: 部署 Seed-OSS-36B
    P6: 尝试 tensor parallel
    P7: 增加长上下文测试
    P8: 设计 BAGEL 多模态 API
