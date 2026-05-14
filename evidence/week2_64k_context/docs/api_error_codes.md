# API 错误码与边界情况说明

## 1. 文档目的

本文档说明 AI Inference Service 在 API 调用、参数校验、后端推理、vLLM 连接和大模型服务运行过程中可能出现的错误类型、当前处理方式和后续改进方向。

本文档用于补充 `docs/api_doc.md`，并回应 Week1 反馈中“API 错误码和边界情况说明可更详细”的改进建议。

当前核心服务链路为：

    Client
    -> FastAPI /generate
    -> app.inference.generate_text()
    -> VLLMBackend
    -> vLLM /v1/chat/completions
    -> Seed-OSS-36B-Instruct
    -> GPU inference

---

## 2. 当前 API Endpoint

| Endpoint | Method | 说明 |
|---|---|---|
| `/health` | GET | FastAPI 服务健康检查 |
| `/generate` | POST | 文本生成接口 |
| `/metrics` | GET | FastAPI Prometheus 指标 |

---

## 3. `/generate` 请求字段

| 字段 | 类型 | 是否必需 | 默认值 | 说明 |
|---|---|---|---|---|
| prompt | string | 是 | 无 | 输入文本 |
| max_new_tokens | integer | 否 | 128 | 最大生成 token 数 |
| temperature | float | 否 | 0.7 | 采样温度 |
| thinking_budget | integer or null | 否 | null | Seed-OSS 推理预算参数 |

示例请求：

    {
      "prompt": "请总结下面这段法律文本。",
      "max_new_tokens": 256,
      "temperature": 0.7,
      "thinking_budget": 512
    }

---

## 4. 错误码总览

| HTTP 状态码 | 场景 | 当前状态 | 后续建议 |
|---|---|---|---|
| 200 | 请求成功 | 已支持 | 保持 |
| 400 | prompt 为空 | 已支持 | 可补充更详细错误信息 |
| 422 | 请求体字段类型错误 | FastAPI/Pydantic 自动支持 | 在文档中给出示例 |
| 500 | 后端推理异常 | 当前主要以 500 暴露 | 后续细分为 502/504/507 |
| 502 | vLLM 服务不可达 | 建议增加 | 明确区分后端不可达 |
| 504 | vLLM 请求超时 | 建议增加 | 明确区分推理超时 |
| 507 | 显存不足/OOM | 文档层说明 | 可用于后续服务化错误映射 |

说明：当前代码中已实现基础错误处理，例如空 prompt 返回 400；部分后端异常当前仍可能表现为 500。后续可以将不同异常类型映射为更细的 HTTP 状态码，提升 API 可运维性。

---

## 5. 200：请求成功

### 场景

FastAPI 成功接收请求，后端模型完成推理，返回结构化结果。

### 返回示例字段

    {
      "response": "...",
      "latency_seconds": 3.36,
      "input_chars": 36,
      "max_new_tokens": 128,
      "thinking_budget": 512,
      "backend": "vllm",
      "input_tokens": 118,
      "output_tokens": 128,
      "tokens_per_second": 38.07,
      "model_name": "ByteDance-Seed/Seed-OSS-36B-Instruct",
      "device": "vllm_server"
    }

---

## 6. 400：prompt 为空

### 场景

请求中 `prompt` 为空字符串、全空格或无有效输入。

错误请求示例：

    {
      "prompt": "   ",
      "max_new_tokens": 128,
      "temperature": 0.7,
      "thinking_budget": 512
    }

### 当前行为

FastAPI 在 API 层拒绝空 prompt，请求不进入后端推理。

### 设计原因

空 prompt 没有实际推理意义，如果继续传入后端，会浪费 GPU 资源并污染 benchmark 数据。

### 建议返回

    {
      "detail": "Prompt cannot be empty."
    }

---

## 7. 422：请求字段类型错误

### 场景

请求字段类型不符合 schema，例如：

1. `max_new_tokens` 传入字符串；
2. `temperature` 传入非数字；
3. `thinking_budget` 传入非法类型；
4. 缺少必需字段 `prompt`。

错误请求示例：

    {
      "prompt": "hello",
      "max_new_tokens": "abc",
      "temperature": 0.7
    }

### 当前行为

FastAPI / Pydantic 自动返回 422 validation error。

### 后续建议

在 API 文档中明确字段类型和取值范围，并在前端或调用脚本中提前做参数检查。

---

## 8. 500：后端推理异常

### 场景

FastAPI 成功接收到请求，但后端推理过程中出现未细分异常。

可能原因：

1. vLLM 返回异常；
2. 模型输出解析失败；
3. token usage 字段缺失或格式异常；
4. Python runtime 异常；
5. 后端配置错误。

### 当前行为

部分异常当前可能以 500 暴露。

### 后续建议

将异常细分为：

1. vLLM 不可达 -> 502；
2. vLLM 超时 -> 504；
3. OOM -> 507；
4. 参数越界 -> 400 或 422；
5. 未知异常 -> 500。

---

## 9. 502：vLLM 服务不可达

### 场景

FastAPI 启动正常，但下游 vLLM server 无法访问。

常见原因：

1. vLLM 尚未完成模型加载；
2. vLLM 进程退出；
3. vLLM 端口错误；
4. `VLLM_BASE_URL` 配置错误；
5. 端口被其他服务占用。

### Week1 实际相关问题

Week1 中曾出现端口 8001 被 nginx 占用，因此 vLLM 改用 8002，并设置：

    VLLM_BASE_URL=http://127.0.0.1:8002/v1

### 后续建议返回

    {
      "detail": "vLLM backend is not reachable."
    }

---

## 10. 504：vLLM 请求超时

### 场景

vLLM 可访问，但请求在规定时间内未返回。

常见原因：

1. 输入上下文过长；
2. max_new_tokens 太大；
3. concurrency 过高；
4. vLLM waiting queue 积压；
5. prefill 阶段耗时过长；
6. GPU 已接近满负载。

### 当前相关配置

FastAPI 侧通过环境变量控制 vLLM 请求超时时间：

    VLLM_TIMEOUT_SECONDS

Week1 Seed-OSS 测试中使用：

    VLLM_TIMEOUT_SECONDS=600

### 后续建议返回

    {
      "detail": "vLLM backend request timed out."
    }

---

## 11. 507：显存不足 / OOM

### 场景

请求或模型加载触发 GPU 显存不足。

常见原因：

1. max_model_len 过大；
2. max_num_batched_tokens 过大；
3. concurrency 过高；
4. 输入上下文过长；
5. max_new_tokens 过大；
6. GPU memory utilization 设置过高；
7. Tensor Parallel 配置不足。

### Week1 资源边界

Seed-OSS-36B-Instruct 在 BF16、TP=2、max_model_len=4096 配置下，稳定运行时每张 A100 80GB 显存约 75.8GB/80GB。

这说明后续 8K/16K/32K 上下文测试和更高并发测试必须逐步推进，不能直接跳到 512K full-context。

### 后续建议返回

    {
      "detail": "GPU memory is insufficient for this request."
    }

---

## 12. 边界情况说明

### 12.1 prompt 过长

如果输入 token 数超过当前 vLLM 启动时的 `MAX_MODEL_LEN`，请求可能失败。

处理建议：

1. 在请求前估算 token 数；
2. 文档中说明当前部署的 `MAX_MODEL_LEN`；
3. 长上下文测试采用 4K/8K/16K/32K 梯度；
4. 失败样本保留到 CSV 和日志。

---

### 12.2 max_new_tokens 过大

过大的 `max_new_tokens` 会增加生成时长、显存压力和 timeout 风险。

处理建议：

1. benchmark 中固定 max_new_tokens；
2. 将短输出和长输出测试分开；
3. 报告中同时记录 output_tokens 和 latency。

---

### 12.3 temperature 取值异常

过高 temperature 会增加输出随机性，不利于性能 benchmark 的可比性。

建议：

1. 性能测试固定 temperature，例如 0.7；
2. 质量测试可单独调整 temperature；
3. 不同实验间避免混用 temperature 配置。

---

### 12.4 thinking_budget 取值异常

`thinking_budget` 是 Seed-OSS 推理预算控制相关参数。

处理建议：

1. 常用测试值为 512 和 1024；
2. 对非 Seed-OSS 模型，不应强制传入 Seed-specific 参数；
3. 对 Seed-OSS 模型，应通过 `chat_template_kwargs.thinking_budget` 传给 vLLM；
4. benchmark 中需要记录 thinking_budget 字段。

---

### 12.5 vLLM 模型名不一致

FastAPI 侧 `VLLM_MODEL_NAME` 必须和 vLLM server 暴露的模型名一致。

检查方式：

    curl http://127.0.0.1:8002/v1/models

如果模型名不一致，vLLM 可能返回 model not found。

---

## 13. Week2 后续改进计划

Week2 中建议将 API 错误处理从文档说明逐步升级为代码实现：

1. 明确区分 502、504、507；
2. 增加更详细的 error response；
3. benchmark CSV 中保留 error_type；
4. 将错误率纳入性能报告；
5. 在 Grafana 中展示 2xx/4xx/5xx 请求比例；
6. 在 FAQ 中关联错误码和排查步骤。

---

## 14. 小结

本项目当前已经具备可运行的 `/generate` 推理接口和基础错误处理。Week2 将进一步补充错误码、边界输入、vLLM 不可达、timeout、OOM 等场景说明，并在后续迭代中将部分文档层错误定义落实到代码层。

API 错误码体系的目标不是只返回错误，而是提升推理服务在高并发、长上下文和多卡部署场景下的可观测性、可排查性和工程可维护性。
