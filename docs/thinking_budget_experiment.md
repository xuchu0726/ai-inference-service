# Thinking Budget 实验说明

## 1. 文档目的

本文档说明 `thinking_budget` 参数在当前 AI Inference Service 中的设计目的、实现状态、已完成实验和后续扩展路线。

PTA 第 1 周任务要求中提到：

    集成推理预算控制（Thinking Budget），实现动态调整推理深度。

当前项目已经完成：

    1. thinking_budget API 参数支持
    2. thinking_budget 后端传递
    3. thinking_budget benchmark 记录
    4. 不同 budget 设置下的本地 benchmark
    5. CX3 vLLM E2E 中 thinking_budget 参数传递

当前尚未完成：

    1. thinking_budget 对模型内部 reasoning tokens 的真实控制
    2. thinking_budget 对生成质量的真实因果影响验证
    3. Seed-OSS-36B 上的原生 budget 控制验证

因此，当前阶段不能声称已经实现了真实模型内部推理深度控制。当前阶段完成的是参数链路、实验框架和后续扩展接口。

---

## 2. 当前系统中的参数链路

`thinking_budget` 当前已经进入完整 API 链路：

    Client request
    → FastAPI /generate
    → app.schemas.GenerateRequest
    → app.main.generate()
    → app.inference.generate_text()
    → backend.generate()
    → API response
    → benchmark record

当前支持该参数的后端：

    1. MockBackend
    2. TransformersBackend
    3. VLLMBackend

这说明 `thinking_budget` 已经不是孤立字段，而是进入了统一推理接口。

---

## 3. API 请求中的 thinking_budget

当前 `/generate` 支持以下请求字段：

    prompt
    max_new_tokens
    temperature
    thinking_budget

请求示例：

    {
      "prompt": "请用三句话解释什么是大模型推理。",
      "max_new_tokens": 128,
      "temperature": 0.7,
      "thinking_budget": 512
    }

其中：

    thinking_budget = 512

表示本次请求使用 512 作为推理预算参数。

当前阶段，该参数会被传入后端并记录在 response 中。

---

## 4. 当前 response 中的 thinking_budget

在 CX3 vLLM E2E 验证中，返回结果包含：

    thinking_budget: 512
    backend: vllm
    model_name: Qwen/Qwen2.5-1.5B-Instruct
    input_tokens: 50
    output_tokens: 128
    tokens_per_second: 53.2239

该结果说明：

    1. FastAPI 成功接收 thinking_budget
    2. app.inference 成功传递 thinking_budget
    3. VLLMBackend 成功接收 thinking_budget
    4. API response 成功返回 thinking_budget
    5. 该字段可用于后续 benchmark 分组

---

## 5. 本地 benchmark 中的 budget 实验

当前本地 TransformersBackend benchmark 已测试 4 组 budget：

    0
    128
    512
    1024

测试 prompt 包括：

    1. 中文大模型推理解释
    2. 中文法律文本风险总结
    3. 英文 KV Cache 解释

实验规模：

    3 prompts × 4 thinking_budget = 12 requests

当前记录字段包括：

    case_id
    prompt_id
    thinking_budget
    status_code
    client_latency_seconds
    server_latency_seconds
    backend
    model_name
    device
    input_chars
    input_tokens
    output_tokens
    tokens_per_second
    max_new_tokens
    response

该实验已证明：

    1. benchmark.py 可以按不同 budget 发起请求
    2. 结果 CSV 可以记录 thinking_budget
    3. analyze_benchmark.py 可以统计 latency、P50、P95、error rate 和 tokens/s
    4. 后续可以复用同一结构测试 vLLMBackend 和 Seed-OSS-36B

---

## 6. 当前实验结果边界

当前本地 benchmark 结果不能解释为：

    thinking_budget 越大，模型推理越深。

原因：

    1. 当前 Qwen2.5-0.5B-Instruct 没有暴露原生 reasoning budget API
    2. 当前 TransformersBackend 没有将 thinking_budget 映射到模型内部推理控制
    3. 当前 VLLMBackend 也没有将 thinking_budget 作为 vLLM 原生参数使用
    4. 当前不同 budget 组的实验主要验证参数链路和记录能力

当前可以准确表述为：

    项目已完成 thinking_budget 参数在 API、后端和 benchmark 中的传递与记录。

不能表述为：

    项目已实现真实 reasoning token budget 控制。

---

## 7. 为什么仍然需要 thinking_budget 参数

虽然当前没有真正控制模型内部 reasoning tokens，但保留该参数仍然有工程价值。

原因：

    1. API schema 已提前兼容后续推理预算控制
    2. benchmark 可以按 budget 分组
    3. 后续切换模型时不需要修改外部 API
    4. 可用于实验不同生成长度和推理策略
    5. 可用于降级策略，例如高负载下降低推理预算
    6. 可用于后续质量-延迟 trade-off 实验

这符合推理服务设计中的 forward-compatible interface 思路。

---

## 8. 后续实现方案

后续可以通过以下方式把 `thinking_budget` 从“记录参数”升级为“真实控制参数”。

### 8.1 映射到 max_new_tokens

最直接方案：

    thinking_budget 越大，max_new_tokens 越大。

示例：

    thinking_budget = 128  → max_new_tokens = 128
    thinking_budget = 512  → max_new_tokens = 512
    thinking_budget = 1024 → max_new_tokens = 1024

优点：

    1. 实现简单
    2. 所有模型都支持
    3. latency 和 output_tokens 会直接变化

缺点：

    1. 这控制的是输出长度，不一定等于 reasoning depth
    2. 不能区分 reasoning tokens 和 final answer tokens

### 8.2 映射到 prompt-level 约束

通过 prompt 控制推理深度：

    Low budget:
        请直接给出简短答案。

    Medium budget:
        请先给出关键理由，再给结论。

    High budget:
        请分步骤分析，再给结论。

优点：

    1. 不依赖模型原生参数
    2. 可用于大多数开源模型
    3. 可以观察生成质量变化

缺点：

    1. 控制不精确
    2. 模型可能不严格遵守

### 8.3 映射到服务降级策略

在高负载下，根据系统状态降低预算：

    低负载:
        thinking_budget = 1024

    中负载:
        thinking_budget = 512

    高负载:
        thinking_budget = 128

用途：

    1. 控制 latency
    2. 控制 GPU token 生成成本
    3. 控制队列积压
    4. 支持高可用降级策略

这与 PTA 第 3 周中的“低预算推理降级策略”可以衔接。

### 8.4 使用模型原生 reasoning budget

如果后续使用支持 reasoning budget 的模型或 API，可以把 `thinking_budget` 映射到模型原生参数。

这是最接近 PTA 原意的方案。

前提：

    1. 模型支持 reasoning token 控制
    2. 推理框架暴露相关参数
    3. response 能区分 reasoning tokens 和 final answer tokens

---

## 9. 后续实验设计

后续应设计两类实验。

### 9.1 性能实验

对不同 budget 记录：

    1. client_latency_seconds
    2. server_latency_seconds
    3. input_tokens
    4. output_tokens
    5. tokens_per_second
    6. P50 latency
    7. P95 latency
    8. error_rate
    9. GPU memory
    10. QPS

目标：

    分析不同 budget 对 latency 和吞吐的影响。

### 9.2 质量实验

对不同 budget 观察：

    1. 答案完整性
    2. 推理步骤数量
    3. 是否覆盖关键点
    4. 是否出现幻觉
    5. 是否符合业务场景要求

测试场景：

    1. 法律文本摘要
    2. 数学推理
    3. 代码生成
    4. 长文本总结
    5. 智能客服问答

目标：

    分析不同 budget 对生成质量的影响。

---

## 10. 与 vLLMBackend 的关系

当前 VLLMBackend 已接收 `thinking_budget`，但没有将其传给 vLLM 原生接口。

当前 VLLMBackend 中真实传给 vLLM 的主要参数是：

    model
    messages
    max_tokens
    temperature

当前 `thinking_budget` 的处理方式：

    1. 接收参数
    2. 保留在服务内部
    3. 返回到 response
    4. 供 benchmark 记录

后续可以增加：

    1. budget 到 max_tokens 的映射
    2. budget 到 prompt template 的映射
    3. budget 到不同 endpoint 或不同模型配置的映射
    4. budget 到高负载降级策略的映射

---

## 11. 与 Seed-OSS-36B 的关系

Seed-OSS-36B 是后续更高价值的目标模型。

在 Seed-OSS-36B 上，thinking_budget 实验应重点验证：

    1. 不同 budget 下的 latency
    2. 不同 budget 下的 output_tokens
    3. 不同 budget 下的生成质量
    4. 长文本处理中的预算影响
    5. 高负载下低 budget 降级是否有效

当前 Qwen2.5-1.5B E2E 验证的意义是：

    先打通 FastAPI + VLLMBackend + vLLM 的参数链路。

后续替换 Seed-OSS-36B 后，可以复用：

    1. /generate API
    2. thinking_budget 字段
    3. VLLMBackend
    4. benchmark 结构
    5. 结果记录字段

---

## 12. 与 PTA 第 1 周要求的对应关系

| PTA 要求 | 当前完成情况 |
|---|---|
| 集成 Thinking Budget | 已完成 API 参数链路 |
| 动态调整推理深度 | 尚未真正控制模型内部 reasoning tokens |
| 设置 512 / 1K tokens | 已支持请求中传入 512 / 1024 等 budget |
| 性能测试对比不同预算 | 本地 TransformersBackend 已完成不同 budget benchmark |
| 生成质量对比 | 初步观察已记录，后续需要更系统评估 |
| 与 Seed-OSS 结合 | 后续在 Seed-OSS-36B 部署后继续验证 |

---

## 13. 阶段结论

当前阶段已经完成 `thinking_budget` 的工程接口和实验记录链路：

    1. FastAPI 支持 thinking_budget
    2. generate_text 传递 thinking_budget
    3. 后端接收 thinking_budget
    4. API response 返回 thinking_budget
    5. benchmark 记录 thinking_budget
    6. 本地 benchmark 已测试 0 / 128 / 512 / 1024
    7. CX3 vLLM E2E 已使用 thinking_budget=512

当前尚未完成真实 reasoning token 控制。

下一步应将 thinking_budget 接入更真实的控制策略：

    1. budget → max_new_tokens
    2. budget → prompt-level 推理深度约束
    3. budget → 高负载降级策略
    4. budget → Seed-OSS 原生 reasoning 控制参数
