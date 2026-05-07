# API 接口文档

## 1. 文档目的

本文档说明 AI Inference Service 当前提供的 RESTful API 接口。

当前项目已经实现统一的文本生成接口 `/generate`，并支持通过配置切换不同推理后端：

    1. MockBackend
    2. TransformersBackend
    3. VLLMBackend

当前最重要的服务链路是：

    Client
    → FastAPI /generate
    → app.inference.generate_text()
    → VLLMBackend
    → vLLM OpenAI-compatible API
    → GPU model
    → structured response

该设计目标是将业务 API 层与底层推理引擎解耦，使项目后续能够从本地小模型迁移到 vLLM、Seed-OSS-36B、Seed-Coder 或 BAGEL 等更复杂模型服务。

---

## 2. GET /health

### 2.1 接口说明

`/health` 用于检查 FastAPI 服务进程是否正常运行。

该接口只代表 FastAPI 应用本身可访问，不代表下游模型服务一定 ready。

在 vLLM 场景下，模型服务 readiness 需要额外检查：

    GET http://127.0.0.1:8001/v1/models

### 2.2 请求方式

    GET /health

### 2.3 返回示例

    {
      "status": "ok"
    }

### 2.4 当前验证结果

在 CX3 E2E 验证中，FastAPI `/health` 已成功返回：

    status: 200
    body: {"status":"ok"}

---

## 3. POST /generate

### 3.1 接口说明

`/generate` 是当前项目的核心推理接口。

该接口接收 prompt 和推理参数，然后根据当前配置选择后端执行文本生成。

当前支持的后端包括：

    1. mock
    2. transformers
    3. vllm

### 3.2 请求方式

    POST /generate
    Content-Type: application/json

### 3.3 请求参数

| 字段 | 类型 | 是否必需 | 默认值 | 说明 |
|---|---|---|---|---|
| prompt | string | 是 | 无 | 输入文本 |
| max_new_tokens | integer | 否 | 128 | 最大生成 token 数 |
| temperature | float | 否 | 0.7 | 采样温度 |
| thinking_budget | integer 或 null | 否 | null | 推理预算参数，用于实验记录和后续推理深度控制 |

### 3.4 请求示例

    {
      "prompt": "请用三句话解释什么是大模型推理。",
      "max_new_tokens": 128,
      "temperature": 0.7,
      "thinking_budget": 512
    }

---

## 4. 返回字段

### 4.1 返回示例

以下是 CX3 上通过 VLLMBackend 成功调用 vLLM 后返回的结构示例：

    {
      "response": "模型生成的文本内容",
      "latency_seconds": 2.404936,
      "input_chars": 36,
      "max_new_tokens": 128,
      "thinking_budget": 512,
      "backend": "vllm",
      "input_tokens": 50,
      "output_tokens": 128,
      "tokens_per_second": 53.2239,
      "model_name": "Qwen/Qwen2.5-1.5B-Instruct",
      "device": "vllm_server"
    }

### 4.2 字段说明

| 字段 | 说明 |
|---|---|
| response | 模型生成文本 |
| latency_seconds | 服务端推理耗时 |
| input_chars | 输入字符数 |
| max_new_tokens | 最大生成 token 数 |
| thinking_budget | 推理预算参数 |
| backend | 当前使用的推理后端 |
| input_tokens | 输入 token 数 |
| output_tokens | 输出 token 数 |
| tokens_per_second | 输出 token 生成速度 |
| model_name | 当前模型名称 |
| device | 当前推理设备或服务位置 |

---

## 5. 后端切换方式

后端通过环境变量控制：

    INFERENCE_BACKEND

当前支持：

| 配置值 | 后端 | 使用场景 |
|---|---|---|
| mock | MockBackend | 不加载模型，仅验证 API 结构 |
| transformers | TransformersBackend | 本地 Hugging Face Transformers 小模型推理 |
| vllm | VLLMBackend | 对接 vLLM OpenAI-compatible server 的 GPU 推理服务 |

### 5.1 MockBackend

用于最早期 API 结构测试。

特点：

    1. 不加载真实模型
    2. 启动快
    3. 适合测试接口格式
    4. 不代表真实推理性能

### 5.2 TransformersBackend

用于本地真实模型推理验证。

当前已验证模型：

    Qwen/Qwen2.5-0.5B-Instruct

当前已验证环境：

    Apple M4
    MPS
    PyTorch
    Hugging Face Transformers

### 5.3 VLLMBackend

用于更接近真实生产推理服务的 GPU serving 场景。

当前已验证模型：

    Qwen/Qwen2.5-1.5B-Instruct

当前已验证环境：

    Imperial CX3
    NVIDIA L40S
    vLLM 0.11.2
    torch 2.9.0+cu128

当前已验证链路：

    FastAPI /generate
    → VLLMBackend
    → vLLM /v1/chat/completions
    → Qwen2.5-1.5B-Instruct
    → NVIDIA L40S

---

## 6. vLLM 相关配置

VLLMBackend 使用以下环境变量：

| 环境变量 | 说明 |
|---|---|
| VLLM_BASE_URL | vLLM OpenAI-compatible API 地址 |
| VLLM_MODEL_NAME | vLLM server 中暴露的模型名 |
| VLLM_TIMEOUT_SECONDS | 请求 vLLM 的超时时间 |

示例：

    INFERENCE_BACKEND=vllm
    VLLM_BASE_URL=http://127.0.0.1:8001/v1
    VLLM_MODEL_NAME=Qwen/Qwen2.5-1.5B-Instruct
    VLLM_TIMEOUT_SECONDS=300

---

## 7. Thinking Budget 当前状态

`thinking_budget` 是当前项目中为推理预算控制预留的参数。

当前已经完成：

    1. API schema 支持 thinking_budget
    2. FastAPI /generate 接收 thinking_budget
    3. generate_text() 向后端传递 thinking_budget
    4. backend.generate() 接收 thinking_budget
    5. API response 返回 thinking_budget
    6. benchmark 可以记录 thinking_budget

当前限制：

    thinking_budget 尚未真正控制模型内部 reasoning tokens。

当前它主要用于：

    1. 参数链路验证
    2. benchmark 分组
    3. 后续推理预算控制实验预留

后续可以将其映射为：

    1. max_new_tokens
    2. prompt-level reasoning length constraint
    3. 模型原生 reasoning budget 参数
    4. 低/中/高推理深度模式
    5. 不同预算下的 latency / tokens/s / 生成质量对比

---

## 8. 错误处理

当前已实现或已观察到的错误处理场景包括：

### 8.1 空 prompt

如果请求中的 prompt 为空字符串，FastAPI 会返回错误。

原因：

    空输入没有实际推理意义，应在 API 层直接拒绝。

### 8.2 不支持的后端配置

如果 `INFERENCE_BACKEND` 设置为未知值，服务会抛出配置错误。

支持值仅包括：

    mock
    transformers
    vllm

### 8.3 vLLM 服务不可达

如果 VLLMBackend 调用 vLLM server 失败，会抛出错误。

已观察到的典型错误：

    ConnectionRefusedError: [Errno 111] Connection refused

根因：

    FastAPI 已启动，但 vLLM 尚未完成模型加载和 API server readiness。

解决方式：

    在部署脚本中轮询 vLLM /v1/models。
    只有 /v1/models 返回 200 后，才启动 FastAPI 并发送 /generate 请求。

详细记录见：

    docs/failure_modes.md
    docs/cx3_vllm_fastapi_e2e.md

---

## 9. 当前已验证 API 结果

### 9.1 本地 TransformersBackend

已完成：

    FastAPI /generate
    → TransformersBackend
    → Qwen/Qwen2.5-0.5B-Instruct
    → Apple MPS

相关文档：

    docs/local_small_model_smoke_test.md
    docs/benchmark_report.md

### 9.2 CX3 VLLMBackend

已完成：

    Python test client
    → FastAPI /generate
    → VLLMBackend
    → vLLM /v1/chat/completions
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S
    → API response

关键结果：

    FastAPI /health: 200
    FastAPI /generate: 200
    client_latency_seconds: 2.408775
    latency_seconds: 2.404936
    input_tokens: 50
    output_tokens: 128
    tokens_per_second: 53.2239
    backend: vllm
    model_name: Qwen/Qwen2.5-1.5B-Instruct
    device: vllm_server

相关文档：

    docs/cx3_vllm_fastapi_e2e.md

---

## 10. 与 第 1 周项目要求的对应关系

| 项目 要求 | 当前 API 完成情况 |
|---|---|
| 封装推理逻辑为 RESTful API | 已完成 FastAPI /generate |
| 支持推理预算控制 | 已完成 thinking_budget 参数链路 |
| 基础功能验证 | 已完成本地 TransformersBackend 与 CX3 VLLMBackend 验证 |
| 错误日志记录 | 已记录 vLLM readiness、CUDA_VISIBLE_DEVICES 等问题 |
| API 接口文档 | 本文档即为 API 接口文档 |
| 初步性能测试 | 已记录 latency、tokens/s、input/output tokens |
