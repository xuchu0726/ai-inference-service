# Seed-OSS-36B 可行性分析与部署路线

## CX3 说明

CX3 是 Imperial College London 的高性能计算集群，通过 PBS 作业系统申请 GPU/CPU/内存资源。本项目将 CX3 用作 GPU、CUDA、vLLM 和端到端推理链路验证平台；由于需要排队且运行结束后服务会释放，Seed-OSS-36B 的长期多卡部署和压测更适合迁移到云 GPU 平台。

---

## 1. 文档目的

本文档用于分析当前项目部署 Seed-OSS-36B 的资源条件、技术风险和实施路线。

本文档用于明确 Seed-OSS-36B 在当前资源条件下的部署策略、阶段安排和风险控制：

    1. 当前 CX3 资源下直接部署 Seed-OSS-36B 的风险
    2. 哪些工作可以先在 CX3 上完成
    3. 哪些工作更适合迁移到云 GPU 上完成
    4. 如何在第 1 周内继续推进 Seed-OSS-36B 短上下文 smoke test
    5. 如何保证当前小模型 vLLM E2E 工作不是偏离主线，而是为 Seed-OSS-36B 部署做准备

当前策略是：

    CX3 继续完成可迁移的基础工程工作；
    云 GPU 并行准备 Seed-OSS-36B 部署尝试；
    不把 Seed-OSS-36B 从路线中移除。

---

## 2. 第 1 周项目任务中的 Seed-OSS 要求

第 1 周任务中与 Seed-OSS 相关的要求包括：

    1. 部署 GPU 环境，适配 Seed-OSS 硬件要求
    2. 加载 Seed-OSS-36B 模型
    3. 验证基础推理能力
    4. 测试长文本处理能力
    5. 封装 RESTful API
    6. 集成 Thinking Budget 参数
    7. 文档中说明 Seed-OSS 的 GQA 注意力机制
    8. 记录模型加载、依赖冲突和环境问题
    9. 输出环境配置指南和初步性能测试报告

当前已完成的基础能力：

    1. CX3 单卡 L40S GPU 验证
    2. CX3 2×L40S GPU 可见性验证
    3. vLLM 0.11.2 环境安装和验证
    4. FastAPI /generate API
    5. VLLMBackend 接入
    6. FastAPI + VLLMBackend + vLLM 的端到端 GPU 推理验证
    7. latency、tokens/s、input/output tokens 记录
    8. CUDA_VISIBLE_DEVICES 和 vLLM readiness 问题记录

当前尚未完成但仍在路线内的目标：

    1. Seed-OSS-36B 模型加载
    2. Seed-OSS-36B 短上下文 smoke test
    3. Seed-OSS-36B 长上下文能力验证
    4. Seed-OSS-36B 不同 thinking_budget 下的延迟和质量对比
    5. Seed-OSS-36B 多卡部署和压测

---

## 3. Seed-OSS-36B 显存粗略估算

Seed-OSS-36B 是 36B 参数规模模型。

如果使用 BF16 或 FP16 精度，仅模型权重显存约为：

    36B parameters × 2 bytes ≈ 72GB

这只是权重本身，不包括推理服务运行时额外开销。

真实 vLLM serving 还需要显存用于：

    1. KV Cache
    2. CUDA context
    3. vLLM runtime overhead
    4. temporary tensors
    5. communication buffer
    6. tensor parallel metadata
    7. prefill 阶段临时显存
    8. batch / concurrency 显存
    9. long-context KV Cache

因此，Seed-OSS-36B 的实际服务化部署显存需求明显高于 72GB。

---

## 4. 当前 CX3 已验证 GPU 资源

### 4.1 单卡 L40S

当前已验证：

    GPU: NVIDIA L40S
    nvidia-smi visible memory: 46068 MiB
    PyTorch visible memory: approximately 44.39GB

结论：

    单卡 L40S 可以用于小模型 vLLM serving、GPU smoke test、E2E 链路验证和 benchmark 流程验证。

但单卡 L40S 不适合完整 BF16 / FP16 加载 Seed-OSS-36B。

原因：

    Seed-OSS-36B 权重估算约 72GB，超过单卡 L40S 可见显存。

### 4.2 双卡 L40S

当前已验证：

    GPU 0: NVIDIA L40S, approximately 44.39GB
    GPU 1: NVIDIA L40S, approximately 44.39GB
    Aggregate visible memory: approximately 88.78GB

结论：

    2×L40S 可以作为 Seed-OSS-36B tensor parallel 短上下文 smoke test 的候选资源。

但风险较高：

    1. 88.78GB 只是总可见显存，不等于可安全服务显存
    2. 权重约 72GB 后，剩余空间需要容纳 KV Cache 和 runtime overhead
    3. 长上下文会进一步扩大 KV Cache
    4. CX3 双卡排队时间不稳定
    5. 不适合长期占用和反复调试

### 4.3 四卡资源

当前观察：

    4GPU 作业在 CX3 上排队时间较长，不适合作为短期主路径依赖。

但这不代表 4GPU 路线无效。

如果 CX3 4GPU 能排到，可以尝试：

    1. vLLM tensor parallel 启动
    2. Seed-OSS-36B 短上下文 smoke test
    3. 显存边界记录
    4. 加载失败原因记录

如果 CX3 4GPU 长时间不可用，应转向云 GPU。

---

## 5. 当前阶段的 Seed-OSS-36B 推进策略

当前使用 Qwen/Qwen2.5-1.5B-Instruct 做 vLLM E2E 验证，是为了先验证可迁移的 serving 架构。

它的作用是先验证可迁移的 serving 架构：

    1. FastAPI 是否能稳定提供 /generate
    2. VLLMBackend 是否能对接 vLLM OpenAI-compatible API
    3. vLLM server 是否能在 GPU 上启动
    4. readiness probe 是否有效
    5. token usage 是否能解析
    6. tokens/s 是否能计算
    7. response 是否能落盘
    8. GPU 显存和利用率是否能记录

这些能力一旦跑通，后续替换为 Seed-OSS-36B 时，不需要推倒重来。

后续主要替换：

    1. VLLM_MODEL_NAME
    2. vLLM --model 参数
    3. tensor_parallel_size
    4. GPU 数量
    5. max_model_len
    6. dtype / quantization
    7. benchmark prompt 和 context length

保留不变：

    1. FastAPI API 层
    2. VLLMBackend
    3. /generate response schema
    4. readiness probe 思路
    5. benchmark 统计方式
    6. failure logging 结构

---

## 6. Seed-OSS-36B 部署尝试路线

当前应采用双线并行路线。

### 6.1 路线 A：CX3 上继续尝试

CX3 上可以继续尝试：

    1. 使用 2×L40S 申请短作业
    2. 使用 vLLM tensor parallel
    3. 降低 max_model_len
    4. 只做短上下文 smoke test
    5. 记录是否能成功加载
    6. 如果失败，记录 OOM、依赖、模型架构、权限或下载问题

CX3 尝试目标不是长时间服务，而是：

    证明能否加载 Seed-OSS-36B；
    或者证明当前资源为什么不足；
    并记录工程证据。

### 6.2 路线 B：云 GPU 上部署

云 GPU 上应作为更稳妥的 Seed-OSS-36B 主部署路线。

推荐资源：

    1. 2×A100 80GB
    2. 4×L40S
    3. 4×A100
    4. 4×H100
    5. 其他可稳定占用的多 GPU 实例

云 GPU 上执行：

    1. 安装 vLLM 环境或使用 Docker
    2. 下载 / 挂载 Seed-OSS-36B 模型
    3. 启动 vLLM tensor parallel
    4. 先跑短上下文 smoke test
    5. 记录显存、latency、tokens/s
    6. 再接入 FastAPI VLLMBackend
    7. 最后做 benchmark 和监控

### 6.3 当前判断

第 1 周仍可以继续推进 Seed-OSS-36B。

但不应将项目主路径依赖于 CX3 4GPU 队列资源。

更合理的是：

    CX3 做基础链路、脚本、文档、benchmark；
    云 GPU 做 Seed-OSS-36B 实际部署尝试。

---

## 7. 单卡、双卡和云 GPU 的任务分工

| 平台 / 资源 | 适合做什么 | 不适合做什么 |
|---|---|---|
| CX3 1×L40S | vLLM 小模型 E2E、benchmark、脚本调试 | Seed-OSS-36B 完整加载 |
| CX3 2×L40S | tensor parallel smoke test、短上下文尝试 | 稳定长服务、长上下文、高并发 |
| CX3 4×L40S | 如果排到，可尝试 Seed-OSS-36B | 不适合依赖为主路径 |
| 云 GPU 2×A100 80GB / 4×L40S+ | Seed-OSS-36B 主部署、压测、演示 | 成本更高，需要控制实验时间 |

---

## 8. GQA 与 Seed-OSS 推理效率说明

第 1 周项目要求文档中说明 Seed-OSS 的 GQA 注意力机制。

GQA 即 Grouped Query Attention，核心思想是：

    多个 query heads 共享较少数量的 key/value heads。

它位于 MHA 和 MQA 之间：

    MHA:
        每个 query head 有独立 key/value head，表达能力强，但 KV Cache 大。

    MQA:
        所有 query heads 共享一组 key/value head，KV Cache 小，但表达能力可能下降。

    GQA:
        将 query heads 分组，共享 key/value heads，在表达能力和推理效率之间折中。

对推理服务的意义：

    1. 减少 KV Cache 显存占用
    2. 降低长上下文 decode 阶段压力
    3. 提升 serving 吞吐潜力
    4. 更适合大模型长上下文推理
    5. 有助于降低高并发推理成本

但必须明确：

    GQA 只能降低 KV Cache 和 attention 相关压力；
    不能消除 36B 模型权重本身的显存需求。

因此，即使 Seed-OSS 使用 GQA，Seed-OSS-36B 仍然需要多 GPU 或量化路线。

---

## 9. 长上下文风险

项目 中提到 Seed-OSS 的长上下文能力。

长上下文推理的主要瓶颈是：

    1. prefill latency
    2. KV Cache memory
    3. GPU memory fragmentation
    4. batch / concurrency 限制
    5. long prompt 的传输和序列化开销

KV Cache 显存通常与以下因素相关：

    sequence length
    × number of layers
    × KV heads
    × head dimension
    × dtype
    × batch size

因此，长上下文验证不能直接从 512K 开始。

合理路线：

    1. 先验证短上下文
    2. 再测试 4K / 8K / 16K
    3. 逐步增加 max_model_len
    4. 每一步记录 GPU memory
    5. 每一步记录 prefill latency
    6. 每一步记录 output latency
    7. 最后再讨论 512K 的可行性

当前第 1 周可做的是：

    先完成长上下文测试设计；
    在可用 GPU 上做较短上下文 smoke test；
    后续云 GPU 再扩大 context length。

---

## 10. vLLM 显存行为对 Seed-OSS 的启示

当前已完成 Qwen2.5-1.5B 的 vLLM E2E 验证。

虽然模型只有 1.5B，但推理后 GPU 显存占用达到：

    39819 MiB / 46068 MiB

原因是 vLLM 会预分配显存用于 KV Cache 和 serving 优化。

日志显示：

    Available KV cache memory: 33.42 GiB
    GPU KV cache size: 1,251,440 tokens
    Maximum concurrency for 4,096 tokens per request: 305.53x

这说明：

    1. vLLM 会主动使用较多显存换取 serving 能力
    2. 显存占用不能只看模型参数量
    3. max_model_len 和 gpu_memory_utilization 会显著影响显存占用
    4. Seed-OSS-36B 的部署必须控制这些参数

后续 Seed-OSS-36B 启动时需要重点调节：

    1. --tensor-parallel-size
    2. --max-model-len
    3. --gpu-memory-utilization
    4. --dtype
    5. --quantization
    6. --max-num-batched-tokens
    7. --enable-prefix-caching

---

## 11. 第 1 周可执行目标

第 1 周剩余时间内，Seed-OSS 路线应继续推进以下任务。

### P0：完成 Seed-OSS-36B 云 GPU 部署准备

包括：

    1. 明确云 GPU 规格
    2. 准备 vLLM 启动命令
    3. 准备 tensor parallel 参数
    4. 准备模型下载 / 挂载路径
    5. 准备短上下文 smoke test prompt
    6. 准备显存和 latency 记录方式

### P1：在 CX3 保留 2GPU / 4GPU 尝试可能

如果 CX3 资源能排到：

    1. 尝试 vLLM tensor parallel
    2. 尝试 Seed-OSS-36B 短上下文加载
    3. 记录成功或失败日志

如果排不到：

    不阻塞项目主线，转向云 GPU。

### P2：先完成 vLLMBackend benchmark

在 Seed-OSS-36B 部署前，先把 benchmark 接到当前 vLLMBackend。

原因：

    benchmark 脚本和统计逻辑后续可直接复用到 Seed-OSS-36B。

### P3：完善文档和交付物

补齐：

    1. API 文档
    2. 架构文档
    3. failure modes 文档
    4. Seed-OSS 可行性文档
    5. thinking_budget 文档
    6. week1_delivery_report

---

## 12. 当前阶段结论

当前结论是采用分阶段部署策略推进 Seed-OSS-36B。

当前结论是：

    1. 单卡 L40S 不适合完整部署 Seed-OSS-36B
    2. 2×L40S 可尝试短上下文 smoke test，但风险较高
    3. CX3 4GPU 不稳定，不应作为唯一主路径
    4. Seed-OSS-36B 仍然是项目目标
    5. 第 1 周仍应准备并尝试云 GPU 部署 Seed-OSS-36B
    6. 当前 Qwen2.5-1.5B vLLM E2E 是 Seed-OSS 部署前的必要工程验证
    7. 当前 FastAPI + VLLMBackend + vLLM 架构可以直接迁移到 Seed-OSS-36B

因此，后续路线应为：

    CX3:
        继续完成基础工程闭环、benchmark、脚本和文档。

    云 GPU:
        尽快尝试 Seed-OSS-36B 短上下文 smoke test，并逐步推进多卡部署、长上下文和压测。

---

## 13. Seed-OSS-36B-Instruct 目标模型确认

本项目的目标模型应统一为：

    ByteDance-Seed/Seed-OSS-36B-Instruct

原因是本项目目标包括：

    1. API serving
    2. 文本生成
    3. 指令跟随
    4. reasoning-style 请求
    5. thinking_budget 控制
    6. 后续长上下文验证
    7. 后续 benchmark 与性能优化

因此，Instruct 版本更符合服务化推理场景。

模型选择边界如下：

| 模型 | 适用场景 | 是否作为本项目主部署目标 |
|---|---|---|
| Seed-OSS-36B-Base | 基座模型研究、下游训练或适配 | 否 |
| Seed-OSS-36B-Base-woSyn | 合成数据影响研究、消融比较 | 否 |
| Seed-OSS-36B-Instruct | 指令跟随、API 调用、文本生成、推理服务 | 是 |

因此，后续脚本、文档和环境变量中的目标模型 ID 应统一为：

    ByteDance-Seed/Seed-OSS-36B-Instruct

Qwen 系列模型只作为 baseline / smoke test 模型，用于验证云 GPU、vLLM、FastAPI 和 benchmark 流程，不应被描述为最终目标模型。

---

## 14. Seed-OSS 专用 vLLM 部署路径

当前项目主线仍然是：

    FastAPI
    -> VLLMBackend
    -> vLLM OpenAI-compatible server
    -> GPU model

这个架构与 Seed-OSS-36B-Instruct 不冲突，不需要推倒重来。

需要区分的是：

    Qwen baseline 启动参数
    Seed-OSS target-model 启动参数

Qwen baseline 用于验证通用 vLLM serving 链路：

    deployment/cloud/run_vllm_qwen_1_5b.sh

Seed-OSS-36B-Instruct 使用专用启动脚本：

    deployment/cloud/run_vllm_seed_oss_36b_tp.sh

Seed-OSS 专用 vLLM 参数包括：

    --enable-auto-tool-choice
    --tool-call-parser seed_oss
    --trust-remote-code
    --tensor-parallel-size
    --max-model-len
    --max-num-batched-tokens
    --gpu-memory-utilization
    --dtype bfloat16

其中：

    --enable-auto-tool-choice
    --tool-call-parser seed_oss
    --trust-remote-code

是 Seed-OSS-Instruct 路线中需要重点保留的模型特定参数。

---

## 15. TP2 脚本定位说明

当前保留：

    deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

但该脚本只作为低资源短上下文实验 wrapper，不是正式完整部署方案。

它的定位是：

    Experimental low-resource TP=2 smoke-test wrapper

适用目标：

    1. 验证模型访问
    2. 验证模型下载
    3. 验证 vLLM 是否能初始化
    4. 验证短上下文 /v1/models readiness
    5. 记录 OOM、依赖、显存或 tensor parallel 问题

不应将 TP=2 描述为 Seed-OSS-36B-Instruct 的推荐完整部署配置。

更正式的多卡部署应使用：

    deployment/cloud/run_vllm_seed_oss_36b_tp.sh

并根据实际 GPU 数量设置：

    TENSOR_PARALLEL_SIZE=4
    TENSOR_PARALLEL_SIZE=8

或其他与云 GPU 资源匹配的 tensor parallel 配置。

---

## 16. thinking_budget 官方传参路径

当前 FastAPI /generate 已经暴露：

    thinking_budget

对于 Qwen baseline，该字段主要作为 API-level 参数和 benchmark 变量记录。

对于 Seed-OSS-36B-Instruct，该字段应作为模型原生推理预算控制参数传给 vLLM。

Seed-OSS 路线下，thinking_budget 应通过 OpenAI-compatible chat completions payload 中的：

    chat_template_kwargs.thinking_budget

传入。

因此，VLLMBackend 已按如下逻辑处理：

    1. 如果模型名包含 Seed-OSS，启用 Seed-OSS thinking budget payload
    2. 如果 VLLM_ENABLE_SEED_THINKING_BUDGET=true，也启用该 payload
    3. 对 Seed-OSS 请求附加 chat_template_kwargs
    4. 对 Qwen / generic baseline 请求不附加该字段，避免兼容性问题

Seed-OSS 请求 payload 结构示意：

    {
        "model": "ByteDance-Seed/Seed-OSS-36B-Instruct",
        "messages": [
            {
                "role": "user",
                "content": "<prompt>"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 128,
        "chat_template_kwargs": {
            "thinking_budget": 512
        }
    }

该设计保证：

    API 层不需要重写；
    benchmark 脚本不需要重写；
    Qwen baseline 不受影响；
    Seed-OSS target path 可以使用模型原生 thinking budget。

---

## 17. 第一阶段 Seed-OSS 部署目标

Seed-OSS-36B-Instruct 支持超长上下文，但第一阶段不应直接从 512K context 开始。

第一阶段目标应设为：

    Seed-OSS-36B-Instruct short-context smoke test

优先验证：

    1. 云 GPU 环境可用
    2. vLLM 版本与模型兼容
    3. 模型权重可下载
    4. tensor parallel 可初始化
    5. /v1/models readiness 可返回
    6. FastAPI + VLLMBackend 可调用
    7. /generate 可返回结果
    8. latency / tokens/s / GPU memory 可记录

推荐第一阶段参数：

    MAX_MODEL_LEN=4096
    MAX_NUM_BATCHED_TOKENS=8192
    DTYPE=bfloat16

在短上下文 smoke test 成功后，再逐步增加：

    1. max_model_len
    2. max_num_batched_tokens
    3. concurrency
    4. prompt length
    5. benchmark request count
    6. long-context test length

这一路线可以避免第一次部署就直接进入不可控的长上下文 OOM 场景。

---

## 18. 当前项目路线结论更新

当前项目路线不是从 Seed-OSS-36B-Instruct 退回到小模型。

更准确的路线是：

    Qwen baseline:
        用于验证 vLLM serving、FastAPI、benchmark、日志和部署流程。

    Seed-OSS target path:
        用于后续目标模型部署、thinking_budget、长上下文和性能优化。

当前 Qwen baseline 的价值在于排除以下基础问题：

    1. 云 GPU 是否可用
    2. CUDA / torch / vLLM 是否可用
    3. FastAPI 是否可调用
    4. VLLMBackend 请求格式是否正确
    5. benchmark 是否能采集 latency / tokens/s / P50 / P95
    6. 日志和结果是否能落盘

这些问题一旦排除，后续切换到 Seed-OSS-36B-Instruct 时，主要变化集中在：

    1. MODEL_NAME
    2. tensor parallel size
    3. max_model_len
    4. max_num_batched_tokens
    5. gpu_memory_utilization
    6. dtype
    7. Seed-specific vLLM flags
    8. thinking_budget payload

因此，当前基础工程工作与 Seed-OSS 目标模型不冲突，而是为 Seed-OSS 多卡部署做准备。
