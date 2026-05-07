# CX3 vLLM + FastAPI 端到端推理验证记录

## CX3 说明

CX3 是 Imperial College London 的高性能计算集群，通过 PBS 作业系统申请 GPU/CPU/内存资源。本项目将 CX3 用作 GPU、CUDA、vLLM 和端到端推理链路验证平台；由于需要排队且运行结束后服务会释放，Seed-OSS-36B 的长期多卡部署和压测更适合迁移到云 GPU 平台。

---

## 1. 文档目的

本文档记录在 Imperial CX3 GPU 节点上完成的 vLLM + FastAPI 端到端推理服务验证。

本次验证的目标不是测试模型能力本身，而是验证以下完整推理服务链路：

    Client
    → FastAPI /generate
    → VLLMBackend
    → vLLM OpenAI-compatible API
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S GPU
    → API response

该链路是后续迁移到云 GPU 并部署 Seed-OSS-36B / Seed-Coder / BAGEL 的工程基础。

---

## 2. 验证环境

本次作业运行于 CX3 GPU 队列。

    Job ID: 2700593.pbs-7
    Host: cx3-20-2
    Queue: v1_gpu72
    GPU: NVIDIA L40S
    GPU memory: 46068 MiB
    Driver Version: 580.82.07
    nvidia-smi CUDA Version: 13.0

Python / 推理环境：

    Python: 3.11.3
    torch: 2.9.0+cu128
    torch CUDA: 12.8
    vLLM: 0.11.2
    CUDA available: True
    CUDA device count: 1
    CUDA device name: NVIDIA L40S

---

## 3. 验证模型

本次使用模型：

    Qwen/Qwen2.5-1.5B-Instruct

选择该模型的原因：

    1. 参数规模较小，适合在单卡 L40S 上进行 serving pipeline 验证
    2. 支持 chat/instruct 形式输入
    3. 可通过 vLLM OpenAI-compatible API 启动
    4. 适合作为后续 Seed-OSS-36B 云端迁移前的低成本链路验证模型

该模型不是项目最终目标模型。最终目标仍是 Seed-OSS-36B / Seed-Coder / BAGEL 等 Seed 系列模型。

---

## 4. 服务架构

本次端到端验证的服务结构如下：

    Python test client
    → http://127.0.0.1:8000/generate
    → FastAPI server
    → app.inference.generate_text()
    → VLLMBackend.generate()
    → http://127.0.0.1:8001/v1/chat/completions
    → vLLM server
    → Qwen2.5-1.5B-Instruct on NVIDIA L40S
    → vLLM response
    → FastAPI response
    → saved JSON result

其中：

    1. FastAPI 负责业务 API 层
    2. VLLMBackend 负责将项目内部 /generate 请求转换为 OpenAI-compatible chat completions 请求
    3. vLLM 负责模型加载、GPU 推理、KV Cache 管理、CUDA Graph 和 token usage 统计
    4. PBS 脚本中的 Python urllib 代码充当临时测试客户端

这种结构比直接在 FastAPI 进程中调用 model.generate 更接近真实大模型推理服务架构。

---

## 5. 作业脚本

验证脚本：

    deployment/vllm/qwen_1_5b_vllm_fastapi_e2e.pbs

该脚本完成以下动作：

    1. 申请 1 张 NVIDIA L40S GPU
    2. 加载 Python / CUDA 环境
    3. 激活 vLLM virtual environment
    4. 设置 INFERENCE_BACKEND=vllm
    5. 启动 vLLM OpenAI-compatible server
    6. 通过 /v1/models 轮询等待 vLLM ready
    7. 启动 FastAPI server
    8. 调用 /health
    9. 调用 /generate
    10. 保存 API response
    11. 记录 nvidia-smi GPU 状态
    12. 关闭 FastAPI 和 vLLM 进程

---

## 6. vLLM readiness 验证

早期脚本只检查 vLLM 进程是否存在，导致 FastAPI 可能在 vLLM 尚未完成模型加载时提前发送请求，从而出现：

    ConnectionRefusedError: [Errno 111] Connection refused

为解决该问题，本次脚本加入 readiness probe：

    GET http://127.0.0.1:8001/v1/models

只有当 /v1/models 返回 200 后，才继续启动 FastAPI 并发送 /generate 请求。

本次结果：

    vLLM server is ready at second 282
    status: 200
    /v1/models returned Qwen/Qwen2.5-1.5B-Instruct

该结果说明 vLLM 已经完成模型加载、初始化和 API server 启动。

---

## 7. vLLM 启动关键日志

本次 vLLM 启动过程中记录到：

    Resolved architecture: Qwen2ForCausalLM
    Using max model len 4096
    dtype=torch.bfloat16
    tensor_parallel_size=1
    pipeline_parallel_size=1
    enable_prefix_caching=True
    enable_chunked_prefill=True
    device_config=cuda

模型加载记录：

    Loading weights took 3.30 seconds
    Model loading took 2.8871 GiB memory and 7.362518 seconds

编译与 warmup 记录：

    torch.compile takes 37.78 s in total
    init engine (profile, create kv cache, warmup model) took 45.12 seconds

KV Cache 记录：

    Available KV cache memory: 33.42 GiB
    GPU KV cache size: 1,251,440 tokens
    Maximum concurrency for 4,096 tokens per request: 305.53x

注意：上述 maximum concurrency 是 vLLM 根据 KV cache capacity 计算出的理论容量指标，不等同于实际业务 QPS。实际 QPS 仍需通过 benchmark / wrk / JMeter 压测验证。

---

## 8. FastAPI 验证结果

FastAPI server 成功启动：

    Uvicorn running on http://127.0.0.1:8000

/health 验证结果：

    status: 200
    body: {"status":"ok"}

说明 FastAPI 服务本身启动正常。

---

## 9. /generate 端到端推理结果

本次通过 FastAPI /generate 发起请求：

    prompt: 请用三句话解释什么是大模型推理，并说明为什么 vLLM 适合做推理服务。
    max_new_tokens: 128
    temperature: 0.7
    thinking_budget: 512

返回状态：

    status: 200

客户端延迟：

    client_latency_seconds: 2.408775

服务端返回字段：

    backend: vllm
    model_name: Qwen/Qwen2.5-1.5B-Instruct
    device: vllm_server
    input_chars: 36
    input_tokens: 50
    output_tokens: 128
    max_new_tokens: 128
    thinking_budget: 512
    latency_seconds: 2.404936
    tokens_per_second: 53.2239

该结果证明：

    1. FastAPI /generate 正常接收请求
    2. app.inference 正确选择 VLLMBackend
    3. VLLMBackend 成功调用 vLLM /v1/chat/completions
    4. vLLM 成功在 GPU 上执行模型推理
    5. token usage 能够返回并被解析
    6. tokens/s 能够被计算并写入 API response

---

## 10. GPU 使用情况

推理后 nvidia-smi 记录：

    GPU: NVIDIA L40S
    GPU memory usage: 39819 MiB / 46068 MiB
    GPU utilization: 63%
    Process: VLLM::EngineCore
    Process GPU memory: 39810 MiB

该结果说明：

    1. 本次不是 mock backend
    2. 本次不是 CPU 推理
    3. 本次不是本地 TransformersBackend
    4. vLLM EngineCore 确实在 GPU 上运行

显存占用较高的主要原因是 vLLM 根据 gpu-memory-utilization 参数预分配大量 KV Cache，以提升 serving 吞吐能力。

---

## 11. 本次验证中的关键问题与解决

### 11.1 CUDA_VISIBLE_DEVICES GPU UUID 问题

CX3/PBS 默认将 CUDA_VISIBLE_DEVICES 设置为 GPU UUID：

    CUDA_VISIBLE_DEVICES=GPU-xxxx

PyTorch 可以识别 GPU UUID，但 vLLM 0.11.2 内部部分逻辑会将该值解析为整数 device id，导致启动失败。

解决方式：

    export CUDA_DEVICE_ORDER=PCI_BUS_ID
    export CUDA_VISIBLE_DEVICES=0

在修改前，通过独立 probe 验证：重映射为 CUDA_VISIBLE_DEVICES=0 后，PyTorch 仍然只看到 PBS 分配的一张 L40S GPU。

### 11.2 vLLM readiness 问题

首次端到端尝试中，FastAPI /health 成功，但 /generate 返回 500。

根因：

    FastAPI 启动时，vLLM 还没有完成模型加载和 API server startup。
    FastAPI 提前调用 vLLM，导致 connection refused。

解决方式：

    轮询 vLLM /v1/models。
    等待 /v1/models 返回 200 后再启动 FastAPI 并发送 /generate 请求。

该问题对应真实生产环境中的服务依赖 readiness probe 和启动编排问题。

---

## 12. 与 第 1 周项目任务的对应关系

| 第 1 周项目任务 | 当前完成情况 |
|---|---|
| 部署 GPU 环境 | 已完成 CX3 单卡 L40S 验证 |
| 安装 PyTorch / CUDA / 推理依赖 | 已完成 Python 3.11 + torch + CUDA + vLLM 环境 |
| 加载模型并验证推理 | 已完成 Qwen2.5-1.5B vLLM GPU 推理 |
| 封装 RESTful API | 已完成 FastAPI /generate |
| 接入 Thinking Budget 参数 | 已通过 /generate 参数链路传递并返回 |
| 错误日志记录 | 已记录 CUDA_VISIBLE_DEVICES 和 readiness 问题 |
| 初步性能记录 | 已记录 latency、tokens/s、input/output tokens、GPU memory |
| Seed-OSS-36B | 受限于 CX3 单卡显存，后续迁移云 GPU 执行 |

---

## 13. 与后续 Seed-OSS-36B 部署的关系

本次验证使用 Qwen2.5-1.5B 作为低成本模型，但服务架构与后续 Seed-OSS-36B 部署保持一致：

    FastAPI
    → VLLMBackend
    → vLLM OpenAI-compatible server
    → GPU model

后续迁移到 Seed-OSS-36B 时，主要需要修改：

    1. VLLM_MODEL_NAME
    2. vLLM --model 参数
    3. tensor_parallel_size
    4. GPU 数量
    5. max_model_len
    6. gpu_memory_utilization
    7. quantization / dtype / KV cache 参数

API 层和 VLLMBackend 不需要推倒重来。

---

## 14. 当前限制

本次验证仍有以下限制：

    1. 只进行了单次请求，不代表高并发能力
    2. 未进行 P50 / P95 benchmark
    3. 未接入 wrk / JMeter / Locust 压测
    4. 未正式部署 Seed-OSS-36B
    5. 未验证长上下文能力
    6. 未验证多模态 BAGEL
    7. 未完成 Prometheus + Grafana 完整监控

这些限制将在后续阶段通过 benchmark、metrics、云 GPU 多卡部署和压测补齐。

---

## 15. 阶段结论

本次验证成功打通了 CX3 单卡 L40S 上的端到端大模型推理服务链路：

    FastAPI
    → VLLMBackend
    → vLLM OpenAI-compatible server
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S GPU

该结果证明项目已经从本地小模型 demo 升级为具备真实 serving 架构的大模型推理服务原型。

本阶段产出的关键工程资产包括：

    1. vLLM serving 脚本
    2. FastAPI + VLLMBackend 代码链路
    3. GPU 推理日志
    4. API response JSON
    5. latency / tokens/s / GPU memory 记录
    6. readiness probe 经验
    7. CUDA_VISIBLE_DEVICES 兼容问题解决记录

下一步应在该链路基础上接入 benchmark.py，进行多请求性能测试，输出 P50 / P95 / error rate / tokens/s，并为后续云 GPU Seed-OSS-36B 部署做准备。
