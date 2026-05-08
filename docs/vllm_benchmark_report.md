> 状态说明：本文档为 vLLM benchmark 方法与字段模板。Seed-OSS-36B-Instruct 的 Week1 实测结果已整理在 `docs/week1_delivery_report.md`。

# vLLMBackend Benchmark Report

## 1. 文档目的

本文档记录 AI Inference Service 在 vLLMBackend 下的推理性能基准测试方案、指标定义、实验方法和结果解释。

本报告对应 第 1 周项目和第 2 周的关键目标：

1. 交付可运行的 API 服务
2. 对推理服务进行性能测试
3. 对比不同 thinking_budget 设置下的响应时间
4. 记录 latency、P50、P95、tokens/s、error_rate
5. 为后续 Seed-OSS-36B、量化、KV Cache、batching 和云 GPU 压测建立 baseline

当前报告定位：

    从单次 E2E smoke test 升级为可重复 benchmark 的性能基线文档。

---

## 2. 当前服务链路

本 benchmark 测试的服务链路为：

    Benchmark Client
    -> FastAPI /generate
    -> app.inference.generate_text()
    -> VLLMBackend.generate()
    -> vLLM /v1/chat/completions
    -> GPU model
    -> vLLM response
    -> FastAPI response
    -> CSV result

该链路与后续 Seed-OSS-36B 云端部署保持一致。

当前可替换组件：

1. 模型名称
2. GPU 规格
3. vLLM 启动参数
4. tensor_parallel_size
5. max_model_len
6. max_new_tokens
7. thinking_budget
8. concurrency

不需要推倒重来的组件：

1. FastAPI API 层
2. VLLMBackend
3. benchmark 脚本
4. 分析脚本
5. CSV 输出结构
6. 报告结构

---

## 3. Benchmark 脚本

原始 benchmark 脚本：

    scripts/benchmark_vllm_backend.py

分析脚本：

    scripts/analyze_vllm_benchmark.py

默认原始结果文件：

    results/vllm_backend_benchmark.csv

默认统计结果文件：

    results/vllm_backend_benchmark_summary.csv

---

## 4. 测试 Prompt

当前 benchmark 使用 4 类 prompt，覆盖推理服务常见输入类型。

### 4.1 大模型推理解释

用途：

    测试中文技术解释能力。

Prompt:

    请用三句话解释什么是大模型推理，并说明为什么 vLLM 适合做推理服务。

### 4.2 法律文本摘要

用途：

    对应 第 1 周项目中的长文本 / 法律文件摘要方向。

Prompt:

    请总结下面这段法律文本的核心风险点：甲方有权单方面修改服务价格，乙方不得提前解除合同，否则需支付违约金。

### 4.3 KV Cache 英文解释

用途：

    测试模型对推理系统概念的英文解释能力。

Prompt:

    Explain KV Cache in LLM inference. Focus on latency, memory usage, and long-context serving.

### 4.4 Seed-OSS 部署规划

用途：

    对应 Seed-OSS-36B 部署、KV Cache、多 GPU 和性能压测方向。

Prompt:

    请从 AI 推理工程角度说明部署 36B 大模型时为什么需要多 GPU、KV Cache 管理和性能压测。

---

## 5. 测试变量

当前 benchmark 支持以下变量。

### 5.1 thinking_budget

默认测试：

    128
    512
    1024

当前阶段说明：

    thinking_budget 已进入 API、后端和 benchmark 记录链路。
    当前尚未等价于模型内部 reasoning token 的原生控制。
    后续可以映射到 max_new_tokens、prompt-level reasoning depth 或 Seed-OSS 原生预算参数。

### 5.2 max_new_tokens

默认值：

    128

后续测试建议：

    64
    128
    256
    512

### 5.3 concurrency

默认值：

    1

后续测试建议：

    1
    2
    4
    8
    16
    32

### 5.4 repeat

默认值：

    1

正式 benchmark 建议：

    repeat >= 2

---

## 6. 记录字段

原始 CSV 记录字段包括：

1. case_id
2. prompt_id
3. thinking_budget
4. concurrency
5. status_code
6. ok
7. client_latency_seconds
8. server_latency_seconds
9. backend
10. model_name
11. device
12. input_chars
13. input_tokens
14. output_tokens
15. tokens_per_second
16. max_new_tokens
17. response
18. error

字段含义：

| 字段 | 含义 |
|---|---|
| case_id | 请求编号 |
| prompt_id | prompt 类型 |
| thinking_budget | 推理预算参数 |
| concurrency | 并发度 |
| status_code | HTTP 状态码 |
| ok | 请求是否成功 |
| client_latency_seconds | 客户端感知 E2E 延迟 |
| server_latency_seconds | 服务端返回的生成延迟 |
| backend | 推理后端 |
| model_name | 模型名称 |
| device | 推理设备 |
| input_chars | 输入字符数 |
| input_tokens | 输入 token 数 |
| output_tokens | 输出 token 数 |
| tokens_per_second | 输出 token 生成速率 |
| max_new_tokens | 最大生成 token 数 |
| response | 模型输出 |
| error | 错误信息 |

---

## 7. Summary 指标

分析脚本输出以下统计指标：

1. total_requests
2. successful_requests
3. failed_requests
4. error_rate
5. concurrency_values
6. backend_values
7. model_name_values
8. device_values
9. client_latency_seconds_avg
10. client_latency_seconds_p50
11. client_latency_seconds_p95
12. client_latency_seconds_min
13. client_latency_seconds_max
14. server_latency_seconds_avg
15. server_latency_seconds_p50
16. server_latency_seconds_p95
17. server_latency_seconds_min
18. server_latency_seconds_max
19. tokens_per_second_avg
20. tokens_per_second_p50
21. tokens_per_second_p95
22. input_tokens_avg
23. output_tokens_avg

---

## 8. 当前限制

当前 benchmark 是非流式请求测试。

因此当前可以准确统计：

1. E2E latency
2. server latency
3. output tokens
4. tokens/s
5. P50 latency
6. P95 latency
7. error_rate

当前不能准确统计：

1. TTFT
2. TPOT
3. ITL
4. streaming token interval

原因：

    TTFT 需要 streaming endpoint 或能够逐 token 接收响应的客户端。
    当前 /generate 接口一次性返回完整 response，因此只能记录完整请求延迟。

后续计划：

    增加 streaming benchmark，单独统计 TTFT、TPOT 和 token interval。

---

## 9. 推荐运行方式

### 9.1 单并发 smoke benchmark

适合第一次验证服务是否正常。

Command:

    python scripts/benchmark_vllm_backend.py \
      --url http://127.0.0.1:8000/generate \
      --concurrency 1 \
      --repeat 1 \
      --max-new-tokens 128 \
      --thinking-budgets 128,512,1024

### 9.2 多并发 baseline benchmark

适合云 GPU 或 CX3 恢复后的正式 baseline。

Command:

    python scripts/benchmark_vllm_backend.py \
      --url http://127.0.0.1:8000/generate \
      --concurrency 4 \
      --repeat 2 \
      --max-new-tokens 128 \
      --thinking-budgets 128,512,1024

### 9.3 生成 summary

Command:

    python scripts/analyze_vllm_benchmark.py \
      --input results/vllm_backend_benchmark.csv \
      --output results/vllm_backend_benchmark_summary.csv

---

## 10. 实验结果记录模板

本节等待实际云 GPU / CX3 benchmark 数据填入。

### 10.1 实验环境

待填写：

1. 平台：
2. GPU 型号：
3. GPU 数量：
4. GPU 显存：
5. NVIDIA driver：
6. CUDA version：
7. Python version：
8. torch version：
9. vLLM version：
10. model_name：
11. max_model_len：
12. gpu_memory_utilization：
13. tensor_parallel_size：

### 10.2 Benchmark 配置

待填写：

1. concurrency：
2. repeat：
3. max_new_tokens：
4. thinking_budgets：
5. prompt count：
6. total_requests：

### 10.3 Summary 结果

待填写：

1. total_requests：
2. successful_requests：
3. failed_requests：
4. error_rate：
5. client_latency_seconds_avg：
6. client_latency_seconds_p50：
7. client_latency_seconds_p95：
8. server_latency_seconds_avg：
9. server_latency_seconds_p50：
10. server_latency_seconds_p95：
11. tokens_per_second_avg：
12. tokens_per_second_p50：
13. tokens_per_second_p95：
14. output_tokens_avg：

---

## 11. 结果分析模板

### 11.1 延迟分析

待填写：

1. P50 latency 代表典型请求体验。
2. P95 latency 代表尾延迟。
3. 如果 P95 明显高于 P50，需要分析是否存在排队、冷启动、batching、GPU memory 或下游 vLLM 波动。

### 11.2 tokens/s 分析

待填写：

1. tokens/s 反映 decode 阶段吞吐。
2. output_tokens 会显著影响 E2E latency。
3. 如果 tokens/s 随并发上升而下降，需要分析 GPU 饱和、KV Cache、batching 和调度开销。

### 11.3 error_rate 分析

待填写：

1. error_rate = failed_requests / total_requests。
2. 如果 error_rate > 0，需要查看 error 字段。
3. 常见错误包括 timeout、vLLM server unavailable、OOM、max_model_len exceeded、HTTP 500。

### 11.4 thinking_budget 分析

待填写：

1. 当前 thinking_budget 主要作为参数链路和实验分组。
2. 后续需要观察不同 budget 对 latency、output_tokens 和质量的影响。
3. 若使用支持 reasoning budget 的模型，需要将该字段映射到模型原生参数。

---

## 12. 与 项目任务的对应关系

| 项目 要求 | 当前 benchmark 对应 |
|---|---|
| 性能测试 | 记录 latency、tokens/s、P50/P95、error_rate |
| Thinking Budget 对比 | 支持 128/512/1024 budget 分组 |
| 初步性能测试报告 | 本文档作为 vLLMBackend baseline report |
| 错误日志记录 | CSV error 字段记录失败原因 |
| 后续高并发压测 | concurrency 参数支持并发请求 |
| Seed-OSS 部署准备 | 同一 benchmark 可复用到 Seed-OSS-36B |

---

## 13. 与 AI Infra 求职目标的关系

该 benchmark 体系直接对应 AI 推理 / AI Infra 岗位中的核心能力：

1. 推理服务性能基准建设
2. latency / P95 / error_rate 指标体系
3. tokens/s 与输出长度分析
4. 后端服务稳定性评估
5. 高并发压测前置能力
6. 云 GPU benchmark 可复现流程
7. Seed-OSS-36B 后续部署实验复用

该报告使项目从“能跑通 API”升级为“能够度量和分析推理服务性能”。

---

## 14. 下一步

后续优先级：

1. 在云 GPU 或 CX3 恢复后运行 vLLMBackend benchmark
2. 生成 results/vllm_backend_benchmark.csv
3. 生成 results/vllm_backend_benchmark_summary.csv
4. 将真实数据填入本报告
5. 增加 streaming benchmark，统计 TTFT / TPOT / ITL
6. 扩展 concurrency = 1 / 2 / 4 / 8 / 16
7. 结合 Prometheus metrics 记录请求数、错误数和 latency histogram
