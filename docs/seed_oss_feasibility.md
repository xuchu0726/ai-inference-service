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

## 2. PTA 第 1 周任务中的 Seed-OSS 要求

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

PTA 第 1 周要求文档中说明 Seed-OSS 的 GQA 注意力机制。

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

PTA 中提到 Seed-OSS 的长上下文能力。

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
