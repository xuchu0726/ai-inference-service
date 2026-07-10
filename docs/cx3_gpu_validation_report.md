# 第 1 周交付报告：GPU 环境验证、vLLM 接入与 Seed-OSS 部署准备

## CX3 说明

CX3 是 Imperial College London 的高性能计算集群，通过 PBS 作业系统申请 GPU/CPU/内存资源。本项目将 CX3 用作 GPU、CUDA、vLLM 和端到端推理链路验证平台；由于需要排队且运行结束后服务会释放，Seed-OSS-36B 的长期多卡部署和压测更适合迁移到云 GPU 平台。

---

## 1. 本周目标

本周目标是完成 AI 推理服务系统的基础环境搭建与服务化能力验证，为后续基于 Seed 系列模型的推理优化、长上下文测试、多卡部署和性能压测做准备。

根据任务要求，本周重点包括：

    1. 部署 GPU 推理环境
    2. 验证 PyTorch / CUDA / vLLM 可用性
    3. 构建 FastAPI RESTful 推理接口
    4. 接入 Thinking Budget 参数链路
    5. 初步验证真实模型推理能力
    6. 记录模型加载、依赖冲突和环境问题
    7. 输出环境配置文档、API 文档和初步性能测试记录

本项目目标不是简单运行一个本地小模型，而是构建一个可迁移到云 GPU、可扩展到 Seed-OSS-36B / Seed-Coder / BAGEL 的大模型推理服务工程原型。

---

## 2. 当前整体进展

截至目前，项目已经完成以下工作：

    1. 搭建 FastAPI 推理服务原型
    2. 实现 /health 和 /generate API
    3. 实现 MockBackend 与 TransformersBackend
    4. 在本地 Apple M4 / MPS 环境下完成 Qwen2.5-0.5B-Instruct 真实模型推理
    5. 实现 benchmark.py，记录 latency、tokens/s、input/output tokens
    6. 实现 analyze_benchmark.py，统计 P50 / P95 / error rate
    7. 在 Imperial CX3 上完成单卡 NVIDIA L40S GPU 验证
    8. 在 CX3 上完成 2×L40S 多 GPU 可见性验证
    9. 在 CX3 上创建 vLLM Python virtual environment
    10. 成功安装并 import vLLM 0.11.2
    11. 接入 VLLMBackend，实现 FastAPI 到 vLLM OpenAI-compatible API 的后端适配
    12. 编写并提交 CX3 GPU / vLLM 环境验证文档
    13. 编写并提交 requirements-vllm.txt
    14. 已完成 FastAPI + VLLMBackend + vLLM server 的端到端链路验证

---

## 3. GPU 环境验证

### 3.1 单卡 L40S 验证

在 CX3 GPU 队列中提交 GPU smoke test 作业，成功获得单卡 NVIDIA L40S。

关键环境信息如下：

    GPU: NVIDIA L40S
    Driver Version: 580.82.07
    nvidia-smi CUDA Version: 13.0
    PyTorch CUDA Version: 12.1 / 12.8
    torch.cuda.is_available(): True
    PyTorch visible GPU memory: approximately 44.39 GB

验证内容包括：

    1. nvidia-smi 可用
    2. Python 环境可用
    3. PyTorch 可识别 GPU
    4. torch.cuda.device_count() 返回 1
    5. GPU tensor matmul 测试成功

该结果证明 CX3 可作为本项目早期 GPU 环境验证和小模型推理服务测试平台。

### 3.2 双卡 L40S 验证

进一步提交 2GPU probe 作业，成功获得 2 张 NVIDIA L40S。

关键结果：

    GPU 0: NVIDIA L40S, visible memory approximately 44.39 GB
    GPU 1: NVIDIA L40S, visible memory approximately 44.39 GB
    Aggregate visible GPU memory: approximately 88.78 GB
    torch.cuda.device_count(): 2
    GPU 0 matmul OK
    GPU 1 matmul OK

该结果说明 CX3 可以支持单节点多 GPU 可见性验证，为后续 vLLM tensor parallel 实验提供基础条件。

但由于队列等待时间不稳定，CX3 不适合作为长期多卡服务平台。后续 Seed-OSS-36B 正式部署和高并发压测应迁移到云 GPU 平台完成。

---

## 4. Seed-OSS-36B 资源评估

任务要求中提到需要加载 Seed-OSS-36B 并验证基础推理能力。经过资源评估，36B 级别模型在 BF16 / FP16 下仅模型权重大约需要：

    36B parameters × 2 bytes ≈ 72 GB

实际部署时还需要额外显存用于：

    1. KV Cache
    2. CUDA context
    3. vLLM runtime overhead
    4. temporary tensors
    5. communication buffer
    6. batch / concurrency memory
    7. long-context prefill memory

因此：

    1. 单卡 L40S 不适合完整部署 Seed-OSS-36B
    2. 2×L40S 可以尝试极短上下文 smoke test，但显存余量较小
    3. 更稳妥方案是 2×A100 80GB、4×L40S、4×A100 或更高规格云 GPU
    4. 512K 长上下文不适合在当前 CX3 单卡/双卡环境中完整验证

基于以上判断，本项目采用两阶段路线：

    CX3:
        验证 GPU 环境、vLLM、FastAPI、VLLMBackend、benchmark 和监控链路

    云 GPU:
        部署 Seed-OSS-36B，执行多卡 tensor parallel、长上下文、benchmark 和最终演示

该路线保证当前工作不会成为一次性 demo，而是为后续高价值云端部署做工程准备。

---

## 5. FastAPI 推理服务封装

项目当前已经实现 FastAPI RESTful 推理接口：

    GET /health
    POST /generate

/generate 接口支持以下参数：

    prompt
    max_new_tokens
    temperature
    thinking_budget

其中 thinking_budget 已经进入 API 参数链路，并在 response 和 benchmark 中记录。当前阶段 thinking_budget 主要作为推理预算控制参数进行传递和实验记录，后续会根据模型能力映射到实际 reasoning tokens、max_new_tokens 或模型特定推理控制参数。

当前后端架构支持：

    1. MockBackend
    2. TransformersBackend
    3. VLLMBackend

其中 VLLMBackend 是本周新增的重要模块。

---

## 6. VLLMBackend 设计

VLLMBackend 的目标是将 FastAPI 服务与 vLLM OpenAI-compatible server 解耦。

当前链路为：

    Client
    → FastAPI /generate
    → app.inference.generate_text()
    → VLLMBackend.generate()
    → vLLM /v1/chat/completions
    → GPU model
    → vLLM response
    → FastAPI response

这种设计比直接在 FastAPI 进程中加载模型更接近真实 LLM serving 架构。

设计优势：

    1. FastAPI 负责业务 API、参数校验、日志、metrics 和后端选择
    2. vLLM 负责高性能模型推理、KV Cache、batching 和 GPU 调度
    3. 业务层与推理引擎解耦
    4. 后续可以替换为 Seed-OSS-36B、Seed-Coder 或其他模型
    5. 后续可以迁移到云 GPU，保持 API 层代码基本不变

当前 VLLMBackend 已实现：

    1. OpenAI-compatible chat completions 请求
    2. max_new_tokens 到 max_tokens 的映射
    3. temperature 参数传递
    4. thinking_budget 参数记录
    5. usage token 解析
    6. latency_seconds 统计
    7. tokens_per_second 计算
    8. backend / model_name / device 字段返回

---

## 7. vLLM 环境验证

在 CX3 上创建 Python virtual environment：

    /rds/general/user/xc1225/home/venvs/vllm-cu121

成功安装：

    vllm==0.11.2
    torch==2.9.0+cu128
    transformers==4.57.6
    triton==3.5.0
    xformers==0.0.33.post1
    flashinfer-python==0.5.2

验证结果：

    vLLM import 成功
    torch.cuda.is_available(): True
    device count: 1
    device name: NVIDIA L40S

该环境不作为跨平台迁移对象。真正可迁移的是：

    1. requirements-vllm.txt
    2. deployment scripts
    3. Dockerfile
    4. README / docs
    5. vLLM 启动参数
    6. benchmark 脚本

---

## 8. 已发现并解决的关键问题

### 8.1 CX3 默认 Python 环境无 torch

首次 GPU smoke test 中发现默认 Python 为系统 Python 3.6.8，且没有 torch。

解决方式：

    1. 使用 module avail 查询可用 Python / CUDA / PyTorch module
    2. 加载 Python/3.11.3-GCCcore-12.3.0
    3. 加载 CUDA module
    4. 在用户目录创建独立 venv
    5. 在 venv 中安装 vLLM 及其依赖

### 8.2 vLLM 与 CUDA_VISIBLE_DEVICES GPU UUID 兼容问题

CX3/PBS 默认将 CUDA_VISIBLE_DEVICES 设置为 GPU UUID，例如：

    CUDA_VISIBLE_DEVICES=GPU-c6724650-8e72-de1b-d306-06289d861c79

PyTorch 可以正常识别该 UUID，但 vLLM 0.11.2 内部部分逻辑会将该值解析为整数 device id，导致：

    ValueError: invalid literal for int() with base 10: 'GPU-...'

解决方式：

    1. 编写 cuda_visible_devices_probe.pbs
    2. 验证 override 前后 PyTorch GPU 可见性
    3. 确认 export CUDA_VISIBLE_DEVICES=0 后仍只暴露 PBS 分配的 1 张 L40S
    4. 在 E2E 脚本中加入：
       export CUDA_DEVICE_ORDER=PCI_BUS_ID
       export CUDA_VISIBLE_DEVICES=0

该问题说明在 HPC/PBS 环境下，GPU UUID、CUDA_VISIBLE_DEVICES 和 vLLM 版本兼容性需要显式验证。

### 8.3 vLLM readiness 问题

首次 E2E 尝试中，FastAPI /health 成功，但 /generate 返回 HTTP 500。

FastAPI log 显示：

    ConnectionRefusedError: [Errno 111] Connection refused
    RuntimeError: vLLM server is not reachable at http://127.0.0.1:8001/v1

vLLM log 显示当时模型仍在 loading checkpoint。

问题原因：

    FastAPI 已启动，但下游 vLLM server 尚未完全 ready。
    脚本提前发送 /generate 请求，导致连接被拒绝。

解决方式：

    将 E2E 脚本的 readiness check 改为轮询：
        http://127.0.0.1:8001/v1/models

只有当 /v1/models 返回成功后，才启动 FastAPI 并发送 /generate 请求。

这对应真实服务中的依赖服务 readiness probe 和启动编排问题。

---

## 9. 当前端到端验证状态

当前正在验证：

    FastAPI
    → VLLMBackend
    → vLLM OpenAI-compatible server
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S GPU

验证脚本：

    deployment/vllm/qwen_1_5b_vllm_fastapi_e2e.pbs

该脚本执行：

    1. 申请 1 张 L40S GPU
    2. 激活 vLLM venv
    3. 设置 HF_HOME 和模型缓存目录
    4. 启动 vLLM server
    5. 等待 /v1/models ready
    6. 启动 FastAPI server
    7. 调用 /health
    8. 调用 /generate
    9. 保存 response、logs 和 GPU 显存信息
    10. 关闭服务并释放 GPU

如果该 E2E 验证成功，则证明项目已经完成从 RESTful API 到 GPU 模型推理的完整服务链路。

---

## 10. 与第 1 周任务要求的对应关系

| 任务要求 | 当前完成情况 |
|---|---|
| 部署 GPU 环境 | 已完成 CX3 单卡 L40S 和 2×L40S 验证 |
| 安装 PyTorch / CUDA 依赖 | 已完成 module 和 venv 验证 |
| 加载 Seed-OSS-36B | 受限于显存，已完成资源评估；正式部署计划迁移至云 GPU |
| 封装 RESTful API | 已完成 FastAPI /generate |
| Thinking Budget | 已完成 API 参数链路和 response 记录 |
| 长文本处理 | 后续在云 GPU / 更大模型上验证 |
| 错误日志记录 | 已记录 CUDA_VISIBLE_DEVICES、readiness、vLLM 启动问题 |
| Prometheus 接入 | 项目已有基础 metrics 结构，后续继续完善 |
| API 文档 | 已有 docs/api_doc.md，后续补充 VLLMBackend |
| 环境配置指南 | 已完成 CX3 GPU / vLLM 环境文档 |
| 初步性能测试报告 | 已有本地 Transformers benchmark；vLLM benchmark 待 E2E 成功后执行 |

---

## 11. 下一步计划

第 1 周后续优先级：

    P0: 完成 Qwen2.5-1.5B vLLM + FastAPI E2E 验证
    P1: 将 E2E 结果写入 docs/cx3_vllm_fastapi_e2e.md
    P2: 扩展 benchmark.py，支持 vLLMBackend 多请求测试
    P3: 输出 vLLM benchmark summary，包括 latency、P50、P95、tokens/s
    P4: 接入 Prometheus metrics，记录请求数、错误数、latency
    P5: 准备云 GPU 部署 Seed-OSS-36B
    P6: 设计 Seed-OSS-36B tensor parallel 启动脚本
    P7: 准备长上下文和 thinking budget 实验

---

## 12. 阶段结论

本周已经完成了从本地小模型推理服务到 GPU/vLLM 推理服务架构的关键升级。

当前项目不再是单纯的 FastAPI demo，而是具备以下工程特征的大模型推理服务原型：

    1. 可插拔推理后端
    2. RESTful API
    3. vLLM OpenAI-compatible serving
    4. GPU 环境验证
    5. 多 GPU 可见性验证
    6. benchmark 基础
    7. error log 和环境问题记录
    8. 面向 Seed-OSS-36B 的资源评估与云 GPU 迁移计划

下一阶段重点是将 E2E serving 链路、benchmark、metrics 和云 GPU 多卡部署串联起来，形成可复现、可观测且可验证的完整工程闭环。

---

## 13. E2E 验证更新：FastAPI + VLLMBackend + vLLM 已跑通

在 Job ID 2700593.pbs-7 中，项目完成了 CX3 单卡 L40S 上的端到端推理服务验证。

验证链路为：

    Python test client
    → FastAPI /generate
    → VLLMBackend
    → vLLM /v1/chat/completions
    → Qwen/Qwen2.5-1.5B-Instruct
    → NVIDIA L40S GPU
    → FastAPI response

关键结果：

    vLLM readiness endpoint: /v1/models returned 200
    FastAPI /health: 200
    FastAPI /generate: 200
    client_latency_seconds: 2.408775
    server latency_seconds: 2.404936
    input_tokens: 50
    output_tokens: 128
    tokens_per_second: 53.2239
    backend: vllm
    model_name: Qwen/Qwen2.5-1.5B-Instruct
    GPU memory after request: 39819 MiB / 46068 MiB
    GPU utilization after request: 63%

该结果证明 FastAPI 业务 API 层、VLLMBackend 适配层、vLLM OpenAI-compatible 推理服务和 GPU 模型推理已经形成完整闭环。

该阶段结果详见：

    docs/cx3_vllm_fastapi_e2e.md
