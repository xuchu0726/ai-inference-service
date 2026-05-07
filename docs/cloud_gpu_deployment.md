# 云 GPU 部署方案：FastAPI + vLLM + Seed-OSS-36B

## 1. 文档目的

本文档记录 AI Inference Service 从本地/CX3 验证阶段迁移到云 GPU 的部署方案。

当前项目目标不是停留在本地小模型调用，而是构建一个面向 AI 推理 / AI Infra 岗位的真实大模型推理服务工程：

    FastAPI
    -> VLLMBackend
    -> vLLM OpenAI-compatible server
    -> cloud GPU
    -> Seed-OSS-36B / Seed-Coder / BAGEL 扩展
    -> benchmark / monitoring / failure analysis

云 GPU 阶段的核心目标是：

1. 运行长期可访问的 vLLM 推理服务
2. 验证 FastAPI + VLLMBackend 的云端 E2E 链路
3. 尝试 Seed-OSS-36B 多卡 tensor parallel 部署
4. 采集 TTFT、E2E latency、P50/P95、tokens/s、error_rate 等指标
5. 为第 2-4 周的性能优化、监控、高并发压测和最终演示做准备

---

## 2. 为什么需要云 GPU

本项目已经完成本地与 CX3 阶段验证，但两者都有明确边界。

本地 Mac 适合：

1. FastAPI API 开发
2. backend abstraction
3. MockBackend / TransformersBackend 验证
4. 小模型 benchmark 脚本开发
5. 文档和部署脚本准备

本地 Mac 不适合：

1. Seed-OSS-36B 完整加载
2. vLLM CUDA serving
3. 多 GPU tensor parallel
4. 高并发真实压测
5. 长上下文显存测试

CX3 适合：

1. GPU 可用性验证
2. CUDA / PyTorch / vLLM 环境验证
3. NVIDIA L40S 单卡/双卡可见性验证
4. 小模型 vLLM E2E smoke test
5. 不花钱的补充实验

CX3 不适合作为主部署平台：

1. GPU 作业需要排队
2. 作业结束后服务进程释放
3. 不适合长期运行 API 服务
4. 不适合稳定压测和演示录制
5. 4GPU 资源不稳定，不应作为主路径依赖

因此，云 GPU 是后续 Seed-OSS-36B 部署、benchmark、监控和演示的主战场。

---

## 3. 云端部署总体架构

云端目标架构：

    Client
    -> FastAPI /generate
    -> app.inference.generate_text()
    -> VLLMBackend.generate()
    -> vLLM /v1/chat/completions
    -> GPU model
    -> vLLM response
    -> FastAPI response
    -> benchmark / metrics / logs

组件职责：

1. FastAPI
   负责业务 API、参数校验、统一 response schema、metrics 和后端切换。

2. VLLMBackend
   负责将项目内部 /generate 请求转换为 vLLM OpenAI-compatible chat completions 请求。

3. vLLM server
   负责模型加载、GPU 推理、KV Cache 管理、batching、prefix caching 和 token usage 返回。

4. benchmark scripts
   负责并发请求、性能数据采集、CSV 落盘和统计分析。

5. Prometheus / Grafana
   后续用于请求量、错误率、latency、tokens、GPU 使用情况的监控展示。

---

## 4. 云端脚本资产

当前新增目录：

    deployment/cloud/

包含：

1. run_vllm_qwen_1_5b.sh
   云端 Qwen2.5-1.5B vLLM baseline 启动脚本。

2. run_fastapi_vllm.sh
   云端 FastAPI 服务启动脚本，使用 VLLMBackend 对接 vLLM server。

3. smoke_test_generate.py
   云端 E2E smoke test 客户端，调用 FastAPI /generate 并保存 response。

4. run_vllm_seed_oss_36b_tp2.sh
   Seed-OSS-36B tensor parallel 启动模板，用于多 GPU 云实例。

5. README.md
   云端部署执行 SOP。

---

## 5. 推荐执行顺序

云端执行不应直接从 Seed-OSS-36B 开始。

正确顺序：

### Step 1：环境检查

检查：

1. GPU 型号
2. GPU 数量
3. GPU 显存
4. NVIDIA driver
5. CUDA version
6. Python version
7. torch version
8. vLLM version
9. 磁盘空间
10. 模型下载权限

### Step 2：Qwen2.5-1.5B vLLM baseline

先启动小模型：

    bash deployment/cloud/run_vllm_qwen_1_5b.sh

目的：

1. 验证云 GPU 可用
2. 验证 CUDA / torch / vLLM
3. 验证 Hugging Face 模型下载
4. 验证 vLLM OpenAI-compatible API
5. 建立云端 serving baseline

### Step 3：FastAPI + VLLMBackend E2E

启动 FastAPI：

    bash deployment/cloud/run_fastapi_vllm.sh

调用：

    python deployment/cloud/smoke_test_generate.py

成功标准：

1. FastAPI /health 返回 200
2. FastAPI /generate 返回 200
3. backend = vllm
4. 返回 input_tokens / output_tokens
5. 返回 tokens_per_second
6. response JSON 保存到 results/

### Step 4：vLLM benchmark

在 smoke test 成功后执行 benchmark。

目标文件：

    scripts/benchmark_vllm_backend.py
    scripts/analyze_vllm_benchmark.py
    results/vllm_benchmark.csv
    results/vllm_benchmark_summary.csv
    docs/vllm_benchmark_report.md

目标指标：

1. TTFT
2. E2E latency
3. P50 latency
4. P95 latency
5. tokens/s
6. error_rate
7. concurrency
8. input_tokens
9. output_tokens

### Step 5：Seed-OSS-36B tensor parallel 尝试

在云端 baseline 跑通后，尝试 Seed-OSS-36B：

    MODEL_NAME=<verified-seed-oss-36b-model-id> \
    TENSOR_PARALLEL_SIZE=2 \
    MAX_MODEL_LEN=4096 \
    bash deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

第一目标不是直接测试 512K 长上下文，而是：

1. 模型能否下载
2. 模型能否加载
3. tensor parallel 能否初始化
4. 短上下文能否生成
5. 显存占用是多少
6. latency / tokens/s 是多少

---

## 6. Seed-OSS-36B 多卡部署策略

Seed-OSS-36B 是 36B 参数规模模型。

BF16 / FP16 权重显存粗略估算：

    36B parameters × 2 bytes ≈ 72GB

真实 serving 还需要额外显存：

1. KV Cache
2. CUDA context
3. vLLM runtime overhead
4. temporary tensors
5. communication buffer
6. tensor parallel metadata
7. prefill 阶段中间状态
8. batch / concurrency 显存

因此，Seed-OSS-36B 不应在单卡 48GB GPU 上完整部署。

推荐云端资源：

1. 2×A100 80GB
2. 4×L40S
3. 4×A100
4. 4×H100

保守启动参数：

    TENSOR_PARALLEL_SIZE=2
    MAX_MODEL_LEN=4096
    DTYPE=bfloat16
    GPU_MEMORY_UTILIZATION=0.90

后续逐步扩大：

1. max_model_len
2. concurrency
3. max_new_tokens
4. batch size
5. prompt length

---

## 7. 与 AI Infra 求职目标的关系

云 GPU 部署路线直接对应 AI 推理 / AI Infra 岗位能力：

1. 推理服务部署
2. vLLM serving
3. OpenAI-compatible API
4. FastAPI 服务封装
5. GPU 环境诊断
6. 多卡 tensor parallel
7. KV Cache 显存分析
8. TTFT / P95 / tokens/s benchmark
9. failure modes 记录
10. 云端部署 SOP

这比单纯本地调用模型更接近真实大模型推理工程。

---

## 8. 和同类 项目任务的融合点

本项目吸收同类 AI Infra 项目 中的硬核能力点：

1. 云端在线推理服务部署
2. 基准性能测试
3. TTFT / throughput / E2E latency 指标体系
4. batching / KV Cache / PagedAttention 机制分析
5. 多卡部署
6. 性能瓶颈分析
7. 可复现部署脚本
8. 数据化性能报告

但本项目不照搬 AzureML / ONNXRuntime 路线，而是选择更贴近大模型 serving 的：

    FastAPI + vLLM + Seed-OSS-36B + cloud GPU

这更符合当前 LLM inference serving 的主流工程实践。

---

## 9. 当前阶段结论

云 GPU 部署不是备选路线，而是本项目从验证阶段进入真实推理工程阶段的必要路径。

当前项目已经具备：

1. FastAPI 服务层
2. VLLMBackend 适配层
3. CX3 vLLM E2E 验证
4. Seed-OSS-36B 显存评估
5. failure modes 文档
6. 云端部署脚本雏形

下一步重点：

1. 完成云端 Qwen2.5-1.5B baseline
2. 完成云端 FastAPI + VLLMBackend E2E
3. 扩展 vLLM benchmark
4. 尝试 Seed-OSS-36B tensor parallel short-context smoke test
5. 记录结果并更新 benchmark report

---

## 10. Seed-OSS-36B-Instruct official-aligned deployment path

The target model for this project is:

    ByteDance-Seed/Seed-OSS-36B-Instruct

Qwen models are used only as baseline and smoke-test models. They are not the final target model.

The deployment strategy is separated into two paths:

1. Baseline serving path

        Qwen2.5-7B / Qwen2.5-14B
        -> vLLM
        -> FastAPI + VLLMBackend
        -> benchmark

   Purpose:

        Validate cloud GPU runtime, vLLM serving, FastAPI integration,
        benchmark scripts, logs and result collection.

2. Target Seed-OSS path

        ByteDance-Seed/Seed-OSS-36B-Instruct
        -> vLLM tensor parallel
        -> FastAPI + VLLMBackend
        -> short-context smoke test
        -> long-context and performance benchmark later

   Purpose:

        Align with the 项目 target model and prepare for Seed-OSS long-context,
        thinking-budget and performance optimization experiments.

Seed-OSS-36B-Instruct is not launched with the same generic Qwen startup script. It uses a dedicated script:

    deployment/cloud/run_vllm_seed_oss_36b_tp.sh

This script includes Seed-specific vLLM options:

    --enable-auto-tool-choice
    --tool-call-parser seed_oss
    --trust-remote-code

It also exposes the following deployment variables:

    MODEL_NAME
    TENSOR_PARALLEL_SIZE
    MAX_MODEL_LEN
    MAX_NUM_BATCHED_TOKENS
    GPU_MEMORY_UTILIZATION
    DTYPE

For first feasibility test, the recommended target is not 512K context. The first target is:

    short-context Seed-OSS-36B-Instruct smoke test

A conservative first run is:

    TENSOR_PARALLEL_SIZE=2
    MAX_MODEL_LEN=4096
    MAX_NUM_BATCHED_TOKENS=8192
    DTYPE=bfloat16

The purpose is to verify:

1. model access
2. model download
3. vLLM tensor parallel initialization
4. /v1/models readiness
5. FastAPI + VLLMBackend compatibility
6. /generate response
7. latency / tokens/s / GPU memory logging

Only after this stage succeeds should the project increase:

1. max_model_len
2. max_num_batched_tokens
3. concurrency
4. benchmark scale
5. long-context test length

This avoids turning the first Seed-OSS deployment attempt into an uncontrolled 512K-context OOM test.

---

## 11. Seed-OSS thinking-budget API path

The project already exposes thinking_budget in the FastAPI /generate request schema.

For generic models, thinking_budget is recorded as an API-level parameter.

For Seed-OSS-36B-Instruct, thinking_budget is model-native and should be passed through the vLLM OpenAI-compatible chat completion payload as:

    chat_template_kwargs.thinking_budget

The VLLMBackend has been updated so that Seed-OSS requests include:

    "chat_template_kwargs": {
        "thinking_budget": thinking_budget
    }

This behavior is enabled when:

1. the model name contains Seed-OSS, or
2. VLLM_ENABLE_SEED_THINKING_BUDGET=true

This keeps the Qwen baseline path compatible while preparing the Seed-OSS target path.
