# Benchmark Report

## 1. 实验目的

本报告记录当前 LLM 推理服务在本地真实模型后端下的初步 benchmark 结果，并补充 P50 / P95 latency、错误率和 tokens/s 等基础性能统计。

当前服务链路为：

```text
FastAPI /generate
→ inference.py
→ TransformersBackend
→ Qwen/Qwen2.5-0.5B-Instruct
→ Apple MPS
→ scripts/benchmark.py
→ results/thinking_budget_benchmark.csv
→ scripts/analyze_benchmark.py
→ results/benchmark_summary.csv
```

本阶段目标不是追求模型能力上限，而是验证一个真实 LLM inference service prototype 是否能够完成以下推理工程闭环：

```text
1. HTTP API 推理请求
2. 真实模型生成
3. token 数统计
4. latency 统计
5. tokens/s 统计
6. P50 / P95 latency 统计
7. error rate 统计
8. benchmark 结果 CSV 落盘
9. 实验结果文档化
```

这一步是项目从 mock backend 进入真实 TransformersBackend，并进一步具备基础性能分析能力的关键节点。

---

## 2. 实验环境

```text
设备：Apple M4
内存：24GB
推理设备：MPS
操作系统：macOS
Python 环境：conda base
服务框架：FastAPI
模型框架：PyTorch + Transformers
推理后端：TransformersBackend
测试模型：Qwen/Qwen2.5-0.5B-Instruct
Benchmark 脚本：scripts/benchmark.py
统计脚本：scripts/analyze_benchmark.py
原始结果文件：results/thinking_budget_benchmark.csv
统计结果文件：results/benchmark_summary.csv
```

---

## 3. 实验对象

本次 benchmark 测试的是本地真实模型后端：

```text
backend = transformers
model_name = Qwen/Qwen2.5-0.5B-Instruct
device = mps
```

该模型通过 Hugging Face Transformers 加载，并通过 `model.generate()` 执行真实文本生成。

当前后端不再是 mock backend，因此返回结果中包含真实推理指标：

```text
input_tokens
output_tokens
tokens_per_second
server_latency_seconds
client_latency_seconds
model_name
device
backend
```

---

## 4. 实验变量

本次实验测试 4 组 `thinking_budget`：

```text
0, 128, 512, 1024
```

测试使用 3 类 prompt：

```text
1. 中文大模型推理解释
2. 中文法律文本风险总结
3. 英文 KV Cache 解释
```

总请求数：

```text
3 prompts × 4 thinking_budget = 12 requests
```

当前阶段中，`thinking_budget` 已经完成 API 参数传递和 benchmark 记录，但尚未真正映射到模型内部 reasoning token 控制机制。因此本实验主要验证参数链路、结果记录、真实模型推理能力和性能统计链路。

---

## 5. 测试 Prompt

### Prompt 1：中文大模型推理解释

```text
请用三句话解释什么是大模型推理。
```

### Prompt 2：中文法律文本风险总结

```text
请总结下面这段法律文本的核心风险点：甲方有权单方面修改服务价格，乙方不得提前解除合同，否则需支付违约金。
```

### Prompt 3：英文 KV Cache 解释

```text
Explain KV Cache in LLM inference in simple terms.
```

---

## 6. 记录指标

当前 benchmark 记录以下字段：

```text
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
```

字段含义：

| 字段 | 含义 |
|---|---|
| case_id | 实验请求编号 |
| prompt_id | prompt 类型编号 |
| thinking_budget | 推理预算参数 |
| status_code | HTTP 状态码 |
| client_latency_seconds | 客户端感知端到端请求耗时 |
| server_latency_seconds | 服务端模型生成耗时 |
| backend | 当前推理后端 |
| model_name | 当前模型名称 |
| device | 当前推理设备 |
| input_chars | 输入字符数 |
| input_tokens | 输入 token 数 |
| output_tokens | 输出 token 数 |
| tokens_per_second | 生成阶段 tokens/s |
| max_new_tokens | 最大生成 token 数 |
| response | 模型生成结果 |

---

## 7. 实验结果摘要

本次实验中，全部 12 个请求成功返回：

```text
HTTP 200
```

真实模型后端返回字段包括：

```text
backend = transformers
model_name = Qwen/Qwen2.5-0.5B-Instruct
device = mps
```

部分实验结果如下：

```text
Prompt 1, thinking_budget=0:
client_latency_seconds = 4.5865
server_latency_seconds = 1.4989
input_tokens = 35
output_tokens = 63
tokens_per_second = 42.03

Prompt 1, thinking_budget=128:
client_latency_seconds = 1.2445
server_latency_seconds = 1.2408
input_tokens = 35
output_tokens = 63
tokens_per_second = 50.7757

Prompt 1, thinking_budget=512:
client_latency_seconds = 1.2358
server_latency_seconds = 1.2326
input_tokens = 35
output_tokens = 63
tokens_per_second = 51.1096

Prompt 1, thinking_budget=1024:
client_latency_seconds = 1.1809
server_latency_seconds = 1.1776
input_tokens = 35
output_tokens = 63
tokens_per_second = 53.5
```

```text
Prompt 2, thinking_budget=0:
client_latency_seconds = 3.0095
server_latency_seconds = 3.0064
input_tokens = 55
output_tokens = 128
tokens_per_second = 42.5765

Prompt 2, thinking_budget=128:
client_latency_seconds = 2.5107
server_latency_seconds = 2.5075
input_tokens = 55
output_tokens = 128
tokens_per_second = 51.0465

Prompt 2, thinking_budget=512:
client_latency_seconds = 2.5530
server_latency_seconds = 2.5492
input_tokens = 55
output_tokens = 128
tokens_per_second = 50.2127

Prompt 2, thinking_budget=1024:
client_latency_seconds = 2.5287
server_latency_seconds = 2.5256
input_tokens = 55
output_tokens = 128
tokens_per_second = 50.6817
```

```text
Prompt 3, thinking_budget=0:
client_latency_seconds = 2.5555
server_latency_seconds = 2.5517
input_tokens = 37
output_tokens = 128
tokens_per_second = 50.1624

Prompt 3, thinking_budget=128:
client_latency_seconds = 2.4435
server_latency_seconds = 2.4402
input_tokens = 37
output_tokens = 128
tokens_per_second = 52.4549

Prompt 3, thinking_budget=512:
client_latency_seconds = 2.5646
server_latency_seconds = 2.5610
input_tokens = 37
output_tokens = 128
tokens_per_second = 49.98

Prompt 3, thinking_budget=1024:
client_latency_seconds = 2.5843
server_latency_seconds = 2.5808
input_tokens = 37
output_tokens = 128
tokens_per_second = 49.5975
```

完整原始结果保存在：

```text
results/thinking_budget_benchmark.csv
```

---

## 8. P50 / P95 统计结果

基于 `results/thinking_budget_benchmark.csv`，使用 `scripts/analyze_benchmark.py` 对 12 条真实模型推理请求进行统计，生成统计结果文件：

```text
results/benchmark_summary.csv
```

统计结果如下：

```text
total_requests: 12
successful_requests: 12
failed_requests: 0
error_rate: 0.0

client_latency_avg: 2.416457
client_latency_p50: 2.540872
client_latency_p95: 3.719141

server_latency_avg: 2.156016
server_latency_p50: 2.516544
server_latency_p95: 2.772284

tokens_per_second_avg: 49.510625
tokens_per_second_p50: 50.4472
tokens_per_second_p95: 52.925195
```

### 8.1 延迟统计观察

当前 12 次请求全部成功：

```text
successful_requests = 12
failed_requests = 0
error_rate = 0.0
```

`client_latency_p95 = 3.719141s`，高于 `client_latency_p50 = 2.540872s`，说明当前本地推理服务存在一定尾延迟。

尾延迟主要可能来自：

```text
1. 首次请求冷启动
2. 输出 token 数差异
3. MPS 后端 warm-up
4. Python / HTTP 服务端额外开销
```

`server_latency_p95 = 2.772284s`，说明模型生成阶段仍是主要耗时来源。

### 8.2 tokens/s 统计观察

当前平均生成吞吐为：

```text
tokens_per_second_avg = 49.510625
```

P50 tokens/s 为：

```text
tokens_per_second_p50 = 50.4472
```

P95 tokens/s 为：

```text
tokens_per_second_p95 = 52.925195
```

这说明在本地 Apple M4 + MPS 环境下，0.5B 级别模型可以完成基础推理实验，但该结果不能代表生产级 NVIDIA GPU 推理性能。

### 8.3 当前统计意义

该统计阶段说明项目已经具备基础性能分析能力：

```text
1. 可以从原始 benchmark CSV 中读取实验数据
2. 可以统计成功率和错误率
3. 可以计算平均延迟、P50 latency、P95 latency
4. 可以统计平均 tokens/s、P50 tokens/s、P95 tokens/s
5. 可以输出 summary CSV 供后续报告和图表使用
```

这一步为后续并发压测、QPS 统计和性能图表生成打基础。

---

## 9. 初步观察

### 9.1 首次请求存在明显冷启动开销

第一个请求的 `client_latency_seconds` 明显高于后续同类请求：

```text
Prompt 1, budget=0:
client latency = 4.5865s

Prompt 1, budget=128:
client latency = 1.2445s
```

原因可能包括：

```text
1. TransformersBackend 懒加载模型
2. MPS 后端初始化
3. tokenizer / model cache 初始化
4. PyTorch 首次执行图构建或 kernel warm-up
5. Python 服务端首次请求处理开销
```

这是推理服务中的真实工程现象。后续 benchmark 应该区分：

```text
cold start latency
warm state latency
```

否则 P50/P95 统计会被冷启动请求污染。

---

### 9.2 输出 token 数对生成延迟影响明显

Prompt 1 输出 63 tokens，warm state 下服务端生成耗时约：

```text
1.18s ~ 1.24s
```

Prompt 2 和 Prompt 3 输出 128 tokens，服务端生成耗时约：

```text
2.44s ~ 3.01s
```

这说明输出 token 数是影响生成 latency 的关键变量之一。

在 LLM inference 中，生成阶段通常是逐 token autoregressive decoding，因此 `output_tokens` 与生成耗时强相关。

---

### 9.3 client latency 与 server latency 的差异可以反映服务额外开销

例如：

```text
Prompt 1, budget=128:
client_latency_seconds = 1.2445
server_latency_seconds = 1.2408
```

两者非常接近，说明当前本地服务的 HTTP 和序列化开销较小。

但首次请求：

```text
client_latency_seconds = 4.5865
server_latency_seconds = 1.4989
```

差异更大，说明冷启动阶段包含了模型加载、缓存初始化或其他非 generate 时间开销。

后续应单独记录：

```text
model_load_latency
preprocessing_latency
generation_latency
postprocessing_latency
```

---

### 9.4 当前 thinking_budget 尚未真正影响模型行为

当前 `thinking_budget` 只是作为 API 参数传递并记录，尚未映射到真实模型的 reasoning token 控制机制。

因此，本阶段实验只能说明：

```text
thinking_budget 参数链路已打通
benchmark 能够记录不同 budget 设置
```

不能说明：

```text
不同 thinking_budget 对真实推理质量或延迟有因果影响
```

后续如果使用支持 reasoning budget 的模型或服务，需要进一步实现预算控制逻辑。例如：

```text
1. 将 thinking_budget 映射到 max_new_tokens
2. 使用支持 reasoning token 控制的模型接口
3. 在 prompt 中显式约束推理步骤长度
4. 分离 reasoning tokens 与 final answer tokens
```

---

### 9.5 当前 benchmark 已具备后续扩展基础

当前 CSV 已包含后续性能分析需要的基础字段：

```text
latency
tokens/s
input_tokens
output_tokens
backend
model_name
device
response
```

当前 summary CSV 已包含：

```text
avg latency
P50 latency
P95 latency
error rate
tokens/s avg
tokens/s P50
tokens/s P95
```

后续可以进一步扩展：

```text
throughput
concurrency
QPS
context length
batch size
GPU / memory usage
request_id
```

---

## 10. 当前输出质量观察

### 10.1 中文解释任务

模型能够正常生成中文回答，输出完整，语义基本合理。

### 10.2 法律文本风险总结任务

模型能够识别：

```text
甲方单方面修改价格
乙方不得提前解除合同
违约金约束
```

但回答中存在一定法律理解不严谨问题，例如部分表述出现逻辑混乱。

这说明小模型可以作为工程链路验证模型，但不能代表高质量业务模型。

### 10.3 KV Cache 英文解释任务

模型能够生成结构化英文回答，但对 KV Cache 的解释不够准确，将其部分混同为一般 key-value store/cache。

这说明后续如果用于技术问答，需要更强模型或更严格 prompt / evaluation。

---

## 11. 当前限制

当前实验仍然存在明显限制：

```text
1. 只使用本地 0.5B 小模型，不代表大模型生产性能
2. 当前设备是 Apple MPS，不是 NVIDIA CUDA GPU
3. 当前没有 vLLM continuous batching
4. 当前没有真实 GPU memory 采集
5. 当前没有并发压测
6. 当前已经完成基础 P50 / P95 统计，但样本量较小，尚未覆盖并发场景
7. 当前没有量化对比
8. 当前没有 KV Cache 显存分析
9. 当前没有 batch size 对比
10. 当前没有 context length 对比
11. 当前没有 Seed-OSS-36B 实验
12. 当前没有 BAGEL 多模态实验
```

因此，本报告不能被解读为生产级性能报告。

它的定位是：

```text
本地真实模型推理服务的初步 benchmark 与基础性能统计报告
```

---

## 12. 与 PTA 第 1 周任务的对应关系

当前阶段对应 PTA 第 1 周任务中的以下部分：

| PTA 第 1 周要求 | 当前完成情况 |
|---|---|
| 部署推理环境 | 本地 PyTorch + Transformers + MPS 已验证 |
| 加载模型并验证基础推理能力 | 已通过 Qwen2.5-0.5B-Instruct 验证 |
| 文本生成 | 已完成 |
| FastAPI RESTful API | 已完成 |
| Thinking Budget 参数 | 已完成参数链路和 benchmark 记录 |
| 性能测试 | 已完成 latency / tokens/s / P50 / P95 / error rate 记录 |
| API 文档 | 已有基础文档 |
| 环境记录 | 已有 environment notes 和 smoke test 文档 |
| 初步性能测试报告 | 已完成 benchmark_report.md 和 benchmark_summary.csv |

尚未完成：

```text
1. Seed-OSS-36B 直接加载
2. 512K 长上下文验证
3. GQA 技术说明文档
4. Prometheus 基础监控
5. 错误日志记录
6. 长文本场景系统测试
```

---

## 13. 与求职目标的对应关系

当前阶段已经能够支持以下求职表述：

```text
实现了一个基于 FastAPI 的 LLM 推理服务原型，支持 MockBackend / TransformersBackend 后端切换，并接入 Qwen2.5-0.5B-Instruct 完成本地真实推理。
```

```text
设计 benchmark 脚本记录 client latency、server latency、input/output tokens、tokens/s、backend、model_name 和 device，并将结果保存为 CSV 便于后续分析。
```

```text
实现 benchmark 分析脚本，统计请求成功率、错误率、平均 latency、P50/P95 latency 和 tokens/s，为后续并发压测和性能报告生成打基础。
```

```text
观察到本地真实推理服务中的冷启动延迟、输出 token 数对生成耗时的影响，以及 API 参数链路与真实模型控制逻辑之间的差异。
```

这已经比普通“调用一个模型 API”的项目更有工程含量。

但要达到 AI 推理 / AI Infra 岗位更强竞争力，后续必须继续补：

```text
1. 并发压测
2. QPS / throughput 统计
3. vLLM backend
4. GPU / CUDA 环境实验
5. KV Cache 和 batch 行为分析
6. 量化实验
7. Prometheus / Grafana 可观测性
8. Docker / CX3 部署脚本
```

---

## 14. 下一步计划

下一阶段将围绕推理工程核心指标继续扩展：

```text
1. 实现 benchmark_concurrency.py
2. 增加 QPS / throughput 统计
3. 增加 context length 测试
4. 增加 request_id 和 structured logging
5. 增加 Prometheus-style metrics
6. 在 CX3 / Colab / Cloud GPU 上测试 GPU 后端
7. 接入 vLLMBackend
8. 撰写 Seed-OSS-36B 可行性分析
```

---

## 15. 阶段结论

当前阶段已经完成从 mock backend 到真实 TransformersBackend 的升级，并完成基础 P50 / P95 性能统计。

项目当前具备以下真实推理能力：

```text
1. 通过 FastAPI 接收推理请求
2. 根据配置选择推理 backend
3. 调用真实 Hugging Face 模型进行生成
4. 返回真实模型输出
5. 记录 input_tokens / output_tokens
6. 记录 server latency / client latency
7. 计算 tokens/s
8. 将 benchmark 数据保存为 CSV
9. 基于结果统计 error rate、P50 latency、P95 latency 和 tokens/s
10. 将实验结果整理为 benchmark report
```

这标志着项目已经从 toy-level mock demo 进入真实 LLM inference service prototype 阶段，并开始具备基础性能分析能力。

下一步应继续推进：

```text
并发 benchmark、QPS 统计和高负载下的 P50 / P95 分析。
```