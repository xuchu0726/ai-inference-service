# 问题记录与故障排查

## 1. 文档目的

本文档记录 AI Inference Service 第 1 周开发过程中遇到的环境、依赖、GPU、vLLM、服务启动和资源限制问题。

这份文档的重点不是只记录报错，而是说明：

    1. 问题是什么
    2. 为什么会发生
    3. 如何定位
    4. 如何解决
    5. 对后续 Seed-OSS-36B / vLLM / 云 GPU 部署有什么影响

该文档对应 第 1 周项目要求中的：

    记录并解决模型加载、依赖冲突等环境问题。

---

## 2. 默认 Python 环境不适合推理项目

### 2.1 问题现象

在 CX3 初始环境中，默认 Python 环境无法直接满足当前大模型推理项目需求。

典型问题包括：

    1. 默认 Python 版本较旧
    2. 默认环境中没有 torch
    3. 默认环境不包含 vLLM
    4. 不适合直接运行 GPU 推理服务

### 2.2 问题原因

CX3 是 HPC 集群，不是预配置好的大模型推理平台。

在 HPC 环境中，软件一般通过 module 系统管理。用户不能假设默认 shell 环境已经包含 PyTorch、CUDA、vLLM 或 Transformers。

### 2.3 解决方式

使用 CX3 module 系统加载明确环境。

基础 GPU smoke test 阶段使用：

    module purge
    module load tools/prod
    module load PyTorch/2.1.2-foss-2023a-CUDA-12.1.1

vLLM 环境验证阶段使用：

    module purge
    module load tools/prod
    module load Python/3.11.3-GCCcore-12.3.0
    module load CUDA/12.1.1

然后创建独立 venv：

    python -m venv ~/venvs/vllm-cu121
    source ~/venvs/vllm-cu121/bin/activate
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install vllm

### 2.4 工程结论

在 HPC / 云 GPU / 服务器环境中，必须显式记录：

    1. Python 版本
    2. CUDA 版本
    3. PyTorch 版本
    4. vLLM 版本
    5. GPU 型号
    6. 驱动版本
    7. 环境创建方式

否则实验不可复现。

---

## 3. PyTorch module 与 vLLM venv 的区别

### 3.1 问题现象

CX3 上已经有 PyTorch module，但仍然需要单独创建 vLLM virtual environment。

### 3.2 问题原因

vLLM 依赖一套更复杂的大模型 serving 运行时，包括：

    1. vLLM
    2. PyTorch
    3. Triton
    4. xformers
    5. flashinfer
    6. transformers
    7. fastapi
    8. uvicorn
    9. ray
    10. prometheus_client

这些依赖和集群自带 PyTorch module 不一定完全匹配。

### 3.3 当前结果

vLLM venv 中已验证：

    Python: 3.11.3
    torch: 2.9.0+cu128
    torch CUDA: 12.8
    vLLM: 0.11.2
    GPU: NVIDIA L40S

### 3.4 工程结论

基础 PyTorch GPU 验证和 vLLM serving 验证应该分开做。

一个环境能跑 `torch.cuda.is_available()`，不代表一定能跑 vLLM serving。

---

## 4. vLLM 安装与依赖体积问题

### 4.1 问题现象

安装 vLLM 时会下载大量依赖，包括 PyTorch、CUDA runtime wheels、xformers、Triton、flashinfer 等。

### 4.2 问题原因

vLLM 不是一个轻量级 Python 包，而是完整的大模型推理 serving 框架。

它需要：

    1. GPU kernel 支持
    2. attention backend
    3. CUDA runtime
    4. 分布式通信组件
    5. OpenAI-compatible API server
    6. 高性能推理相关依赖

### 4.3 解决方式

将 vLLM 安装在用户目录下的独立 venv：

    ~/venvs/vllm-cu121

但该 venv 不提交到 Git，也不作为跨平台迁移对象。

真正应该迁移的是：

    1. requirements-vllm.txt
    2. deployment/vllm/*.pbs
    3. 后续 Dockerfile
    4. 文档中的环境版本记录
    5. vLLM 启动命令

### 4.4 工程结论

venv 是当前机器上的运行环境，不是工程交付物。工程交付物应该是可复现环境的配置文件和脚本。

---

## 5. CUDA_VISIBLE_DEVICES GPU UUID 问题

### 5.1 问题现象

第一次启动 vLLM 时失败，日志中出现：

    ValueError: invalid literal for int() with base 10: 'GPU-...'

错误出现在 vLLM 内部 CUDA device capability 检查阶段。

### 5.2 问题原因

CX3 / PBS 默认将 `CUDA_VISIBLE_DEVICES` 设置为 GPU UUID，例如：

    CUDA_VISIBLE_DEVICES=GPU-c6724650-8e72-de1b-d306-06289d861c79

PyTorch 可以识别这种 GPU UUID 格式。

但 vLLM 0.11.2 的部分内部逻辑会把该值当成整数 device id 解析，因此出现：

    int("GPU-...") 失败

### 5.3 定位方式

创建独立 probe 脚本：

    deployment/vllm/cuda_visible_devices_probe.pbs

该脚本验证：

    1. PBS 默认 CUDA_VISIBLE_DEVICES 是 GPU UUID
    2. PyTorch 在 UUID 格式下可以看到 L40S
    3. 将 CUDA_VISIBLE_DEVICES 改成 0 后，PyTorch 仍然只看到 PBS 分配的 GPU
    4. 该修改不会越权看到其他 GPU

### 5.4 解决方式

在 vLLM 启动前加入：

    export CUDA_DEVICE_ORDER=PCI_BUS_ID
    export CUDA_VISIBLE_DEVICES=0

### 5.5 当前结果

修改后，vLLM 可以成功识别 Qwen2ForCausalLM，并进入模型加载流程。

### 5.6 工程结论

HPC 调度系统给出的 GPU 可见性配置不一定和推理框架完全兼容。

在 vLLM / TensorRT-LLM / SGLang 等推理框架上，需要额外验证：

    1. CUDA_VISIBLE_DEVICES
    2. device id 映射
    3. 多卡可见性
    4. tensor parallel 对 device id 的要求

---

## 6. vLLM readiness 问题

### 6.1 问题现象

第一次端到端测试中：

    FastAPI /health 成功
    FastAPI /generate 返回 HTTP 500

FastAPI log 显示：

    ConnectionRefusedError: [Errno 111] Connection refused

项目中的 VLLMBackend 报错：

    vLLM server is not reachable at http://127.0.0.1:8001/v1

### 6.2 问题原因

FastAPI 已经启动，但 vLLM 还没有真正 ready。

vLLM 启动过程包括：

    1. 启动 API server 进程
    2. 解析模型架构
    3. 加载权重
    4. 初始化 distributed backend
    5. 创建 KV Cache
    6. 执行 torch.compile
    7. CUDA Graph capture
    8. 注册 OpenAI-compatible API routes
    9. 开始监听请求

因此，vLLM 进程存在，不代表 `/v1/chat/completions` 已经可用。

### 6.3 解决方式

修改 E2E 脚本，增加 vLLM readiness probe：

    GET http://127.0.0.1:8001/v1/models

只有当 `/v1/models` 返回 200 后，才继续：

    1. 启动 FastAPI
    2. 请求 FastAPI /health
    3. 请求 FastAPI /generate

### 6.4 当前结果

修复后成功：

    vLLM server is ready at second 282
    /v1/models returned 200
    FastAPI /health returned 200
    FastAPI /generate returned 200

### 6.5 工程结论

服务进程启动和服务可用是两回事。

真实推理系统必须区分：

    1. liveness
    2. readiness
    3. downstream dependency readiness

在当前项目中：

    FastAPI /health
        只说明 FastAPI 活着。

    vLLM /v1/models
        说明模型服务已经 ready。

---

## 7. vLLM 冷启动时间问题

### 7.1 问题现象

本次 CX3 E2E 中，vLLM readiness 时间为：

    282 seconds

约 4 分 42 秒。

### 7.2 原因分析

日志显示启动过程包含：

    1. 模型架构解析
    2. 模型权重加载
    3. torch.compile
    4. KV Cache 创建
    5. CUDA Graph capture
    6. vLLM API server readiness

其中日志记录：

    torch.compile takes 37.78 s in total
    init engine took 45.12 seconds
    Model loading took 2.8871 GiB memory and 7.362518 seconds

### 7.3 工程结论

LLM serving 需要区分：

    1. cold start latency
    2. warm inference latency

当前一次请求 latency 约 2.4s，但服务冷启动接近 5 分钟。

这在生产服务中意味着：

    1. 不能频繁重启模型服务
    2. 需要 readiness probe
    3. 需要预热
    4. 需要实例生命周期管理
    5. 高可用服务需要滚动更新或预启动实例

---

## 8. vLLM 显存占用高的问题

### 8.1 问题现象

本次使用 Qwen2.5-1.5B-Instruct，但推理后 GPU 显存占用为：

    39819 MiB / 46068 MiB

这明显高于模型权重大小。

### 8.2 原因分析

vLLM 会根据配置预分配显存用于 KV Cache 和 serving 优化。

当前启动参数中使用了：

    gpu_memory_utilization = 0.85
    max_model_len = 4096

vLLM 日志显示：

    Available KV cache memory: 33.42 GiB
    GPU KV cache size: 1,251,440 tokens
    Maximum concurrency for 4,096 tokens per request: 305.53x

### 8.3 工程结论

在 vLLM 中，显存占用不能只按模型权重估算。

需要同时考虑：

    1. 模型权重
    2. KV Cache
    3. CUDA context
    4. runtime overhead
    5. CUDA Graph
    6. batch 和并发
    7. max_model_len

这也解释了为什么 Seed-OSS-36B 不能只按 72GB 权重估算来判断可部署性。

---

## 9. CX3 队列和资源限制

### 9.1 问题现象

当前观察到：

    1. 1GPU 作业相对可排到
    2. 2GPU 作业等待时间不稳定
    3. 4GPU 作业基本不可依赖
    4. 作业结束后 GPU 资源自动释放

### 9.2 原因

CX3 是共享 HPC 集群，通过 PBS 调度资源，不适合长期占用 GPU 运行 API 服务。

### 9.3 工程判断

CX3 适合：

    1. GPU 环境验证
    2. vLLM 安装验证
    3. 小模型 E2E smoke test
    4. benchmark 流程验证
    5. 部署脚本调试
    6. 文档沉淀

CX3 不适合：

    1. 长期运行 API 服务
    2. Seed-OSS-36B 稳定部署
    3. 长时间多卡调试
    4. 生产式高并发压测
    5. 最终演示平台

### 9.4 后续路线

后续应迁移到云 GPU 平台完成：

    1. Seed-OSS-36B 部署
    2. 多卡 tensor parallel
    3. 长上下文测试
    4. Prometheus / Grafana
    5. wrk / JMeter / Locust 压测
    6. 最终演示视频

---

## 10. Seed-OSS-36B 显存风险

### 10.1 问题

项目任务要求基于 Seed-OSS-36B 等 Seed 系列模型，但当前 CX3 单卡 L40S 无法稳定完整部署 36B 模型。

### 10.2 粗略显存估算

Seed-OSS-36B 如果使用 BF16 / FP16，仅权重约需要：

    36B parameters × 2 bytes ≈ 72GB

但实际 serving 还需要：

    1. KV Cache
    2. CUDA context
    3. vLLM runtime overhead
    4. communication buffer
    5. temporary tensors
    6. long-context prefill memory
    7. batch / concurrency memory

### 10.3 当前资源对比

当前已验证：

    单卡 L40S:
        PyTorch 可见显存约 44.39GB

    2×L40S:
        总可见显存约 88.78GB

判断：

    1. 单卡 L40S 不足以完整加载 Seed-OSS-36B
    2. 2×L40S 可能仅适合极短上下文 smoke test
    3. 2×L40S 对高并发和长上下文风险很高
    4. 4GPU 或 A100 80GB 级别资源更合理

### 10.4 工程结论

当前先用 Qwen2.5-1.5B 打通 vLLM serving 架构是合理路线。

该路线是先完成可迁移服务骨架，再在更合适的云 GPU 上切换到 Seed-OSS-36B 目标模型。

---

## 11. GitHub 认证问题

### 11.1 问题现象

在 CX3 上 push 到私人 GitHub 仓库时出现：

    Permission to xuchu0726/ai-inference-service.git denied to ada-xc1225

以及：

    Password authentication is not supported for Git operations.

### 11.2 问题原因

CX3 上 GitHub 认证最初使用的是学校 GitHub 身份或缓存身份 `ada-xc1225`，而目标仓库属于私人账号 `xuchu0726`。

GitHub HTTPS push 也不再支持账号密码，需要 Personal Access Token。

### 11.3 解决方式

修改 remote：

    git remote set-url origin https://xuchu0726@github.com/xuchu0726/ai-inference-service.git

然后使用 GitHub Personal Access Token 完成认证。

### 11.4 当前结果

已成功 push 到：

    https://github.com/xuchu0726/ai-inference-service.git

### 11.5 工程结论

在学校集群上开发私人项目时，必须确认：

    1. git remote 指向私人仓库
    2. git push 使用正确 GitHub 身份
    3. 不要误 push 到课程作业仓库
    4. 不要污染学校评分仓库

---

## 12. 当前问题记录汇总

| 问题 | 状态 | 解决方式 |
|---|---|---|
| 默认 Python 不适合推理项目 | 已解决 | 使用 module 和 venv |
| PyTorch module 与 vLLM 依赖不一致 | 已解决 | 独立 vLLM venv |
| vLLM 安装依赖复杂 | 已处理 | requirements-vllm + 文档记录 |
| CUDA_VISIBLE_DEVICES GPU UUID 导致 vLLM 报错 | 已解决 | 重映射为 CUDA_VISIBLE_DEVICES=0 |
| FastAPI 提前请求 vLLM 导致 500 | 已解决 | 增加 /v1/models readiness probe |
| vLLM 冷启动时间长 | 已记录 | 区分 cold start 与 warm latency |
| vLLM 显存占用高 | 已解释 | KV Cache 和 gpu_memory_utilization |
| CX3 多卡排队不稳定 | 已判断 | CX3 做验证，云 GPU 做主部署 |
| Seed-OSS-36B 单卡不可行 | 已评估 | 后续云 GPU + tensor parallel |
| GitHub 身份错误 | 已解决 | 改 remote + PAT |

---

## 13. 对后续工程的影响

这些问题直接影响后续设计：

    1. 所有服务脚本必须包含 readiness probe
    2. vLLM 启动前必须确认 CUDA_VISIBLE_DEVICES 格式
    3. benchmark 应区分冷启动和 warm request
    4. Seed-OSS-36B 必须做资源评估，不能盲目启动
    5. CX3 适合作为验证平台，不适合作为最终长期服务平台
    6. 云 GPU 部署必须用 requirements / Dockerfile 固化环境
    7. 所有关键实验要写入文档，避免只留下终端输出

---

## 14. 阶段结论

第 1 周遇到的问题不是无效消耗，而是大模型推理服务工程中真实存在的问题：

    1. 环境隔离
    2. GPU 可见性
    3. CUDA / PyTorch / vLLM 版本匹配
    4. 服务启动顺序
    5. 模型服务 readiness
    6. 显存预估
    7. 资源调度
    8. Git 身份管理

当前所有关键问题均已记录，并且核心阻塞项已经解决。

项目已经完成：

    FastAPI
    → VLLMBackend
    → vLLM server
    → Qwen2.5-1.5B
    → NVIDIA L40S

的端到端 GPU 推理验证。

下一步重点是把该链路扩展为多请求 benchmark，并为云 GPU 上的 Seed-OSS-36B 部署做准备。
