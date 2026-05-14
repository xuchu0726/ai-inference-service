# AI Inference Service

一个面向 **AI 推理工程 / LLM Serving / AI Infra** 方向的推理服务原型项目。

本项目目标不是做一个普通聊天机器人 demo，而是构建一个可运行、可压测、可扩展、可文档化的大模型推理服务，用于系统性训练和展示以下能力：

- 模型服务化
- 推理接口封装
- 可插拔推理后端
- Thinking Budget 推理预算控制
- Benchmark 数据采集
- 延迟、吞吐、P50/P95、tokens/s 等指标分析
- 并发压测
- GPU 推理实验
- KV Cache、Batch、量化等推理优化分析
- Prometheus-style 监控
- Docker / CX3 / Cloud GPU 部署准备
- 技术文档、实验报告和失败复盘

当前项目处于早期阶段，已经完成 FastAPI 服务骨架、MockBackend、Thinking Budget 参数传递、benchmark 脚本、CSV 结果保存、实验说明文档和 GitHub 版本管理。后续将逐步接入 Transformers 小模型、vLLM 后端、GPU benchmark、并发压测、Prometheus 指标和部署脚本。

---

## 1. 项目定位

本项目用于补齐 AI 推理 / AI Infra 求职中的工程短板，重点不在于做一个表层应用，而在于理解和验证大模型推理服务中的关键工程问题：

- 如何封装 LLM 推理服务
- 如何设计可切换的推理 backend
- 如何设计 benchmark 实验
- 如何衡量 latency / throughput / tokens/s / GPU memory
- 如何分析 batch、context length、KV Cache、量化之间的 trade-off
- 如何将实验结果沉淀成可复现的工程文档
- 如何从本地 mock 服务逐步扩展到真实模型、vLLM 和 GPU 环境

---

## 2. 当前已完成功能

当前已经完成：

- FastAPI 服务
- `/health` 健康检查接口
- `/generate` 推理接口
- 可插拔 backend 初始架构
- MockBackend
- `thinking_budget` 参数
- benchmark 脚本
- benchmark 结果保存为 CSV
- Thinking Budget 实验说明文档
- GitHub 版本管理

当前尚未完成：

- 真实小模型推理后端
- TransformersBackend
- vLLMBackend
- GPU benchmark
- 并发压测
- P50 / P95 latency 统计
- Prometheus-style metrics
- Docker 部署
- Seed-OSS-36B 可行性实验
- BAGEL 多模态 PoC

---

## 3. 项目结构

```text
ai-inference-service/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── schemas.py
│   ├── config.py
│   ├── inference.py
│   │
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── mock_backend.py
│   │   ├── transformers_backend.py
│   │   └── vllm_backend.py
│   │
│   ├── metrics/
│   │   ├── __init__.py
│   │   └── prometheus_metrics.py
│   │
│   └── utils/
│       ├── __init__.py
│       └── logging_utils.py
│
├── scripts/
│   ├── benchmark.py
│   ├── benchmark_concurrency.py
│   ├── gpu_smoke_test.py
│   └── plot_results.py
│
├── deployment/
│   ├── Dockerfile
│   ├── run_local.sh
│   └── cx3_gpu_smoke.pbs
│
├── docs/
│   ├── api_doc.md
│   ├── environment_notes.md
│   ├── week1_plan.md
│   ├── thinking_budget_experiment.md
│   ├── architecture.md
│   ├── benchmark_report.md
│   ├── failure_modes.md
│   └── seed_oss_feasibility.md
│
├── results/
│   ├── mock_benchmark.csv
│   └── thinking_budget_benchmark.csv
│
├── tests/
│   ├── __init__.py
│   └── test_api.py
│
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 4. 当前运行方式

### 4.1 安装依赖

```bash
pip install -r requirements.txt
```

### 4.2 启动服务

```bash
uvicorn app.main:app --reload
```

服务启动后，默认运行在：

```text
http://127.0.0.1:8000
```

### 4.3 查看 API 文档

打开：

```text
http://127.0.0.1:8000/docs
```

### 4.4 运行 benchmark

保持 FastAPI 服务运行，然后在另一个终端执行：

```bash
python scripts/benchmark.py
```

当前 benchmark 输出文件：

```text
results/thinking_budget_benchmark.csv
```

---

## 5. API 接口

### 5.1 GET `/health`

健康检查接口。

示例返回：

```json
{
  "status": "ok"
}
```

### 5.2 POST `/generate`

推理接口。

示例请求：

```json
{
  "prompt": "请用三句话解释什么是大模型推理。",
  "max_new_tokens": 128,
  "temperature": 0.7,
  "thinking_budget": 128
}
```

示例返回：

```json
{
  "response": "[Mock Output] Received prompt with 16 characters. max_new_tokens=128, temperature=0.7, thinking_budget=128.",
  "latency_seconds": 0.000002,
  "input_chars": 16,
  "max_new_tokens": 128,
  "thinking_budget": 128,
  "backend": "mock"
}
```

---

## 6. 当前实验：Thinking Budget Benchmark

当前实验测试 4 组 `thinking_budget`：

```text
0, 128, 512, 1024
```

测试使用 3 条 prompt：

1. 中文大模型推理解释 prompt
2. 中文法律文本摘要 prompt
3. 英文 KV Cache 解释 prompt

因此总实验记录数为：

```text
3 个 prompt × 4 个 thinking_budget = 12 条记录
```

当前记录字段包括：

- `case_id`
- `prompt_id`
- `thinking_budget`
- `status_code`
- `client_latency_seconds`
- `server_latency_seconds`
- `input_chars`
- `max_new_tokens`
- `response`

当前生成结果文件：

```text
results/thinking_budget_benchmark.csv
```

说明：当前后端仍为 mock backend，因此该实验主要验证 benchmark 框架、参数传递链路和结果落盘流程。接入真实模型后，将进一步记录：

- output tokens
- tokens/s
- P50 / P95 latency
- GPU memory
- error rate
- 输出质量差异

---

## 7. Backend 设计

当前已经初步拆分出可插拔推理后端结构：

```text
app/backends/
├── base.py
├── mock_backend.py
├── transformers_backend.py
└── vllm_backend.py
```

当前默认后端：

```text
MockBackend
```

后续计划支持：

- TransformersBackend：用于本地或 Colab/CX3 上的小模型推理
- vLLMBackend：用于更接近真实 LLM serving 的 GPU 推理服务
- Seed-OSS-compatible backend：用于后续 Seed-OSS-36B 可行性实验

目标是让 API 层保持稳定，通过替换 backend 来支持不同推理引擎。

---

## 8. 后续路线

### Stage 1：真实小模型后端

目标：从 mock backend 升级到真实 Transformers backend。

计划接入：

- Qwen2.5-0.5B-Instruct
- 或其他可在本地 / Colab / CX3 上运行的小模型

核心链路：

```text
prompt → tokenizer → model.generate → decode → API response → benchmark CSV
```

---

### Stage 2：推理性能 Benchmark

目标：对齐 AI 推理岗位核心指标。

计划实现：

- P50 / P95 latency
- throughput
- tokens/s
- context length 对性能影响
- thinking_budget 对 latency 和输出质量的影响
- concurrency 对延迟和吞吐的影响

---

### Stage 3：GPU / vLLM 实验

目标：接近真实 LLM serving 场景。

计划实现：

- CX3 / Colab / Cloud GPU smoke test
- vLLM backend
- GPU memory 记录
- batch / concurrency 实验
- KV Cache 行为分析
- Seed-OSS-36B 可行性评估

---

### Stage 4：工程化与可观测性

目标：从脚本 demo 升级为工程服务。

计划实现：

- structured logging
- request_id
- error handling
- timeout handling
- Prometheus-style metrics
- Dockerfile
- deployment guide
- failure_modes.md
- architecture.md

---

### Stage 5：Seed-OSS / 多模态扩展

目标：对齐 项目 原始任务书中的 Seed 模型、多模态和长上下文方向。

计划探索：

- Seed-OSS-36B 部署可行性分析
- GQA / KV Cache / 长上下文推理约束分析
- Seed-Coder 代码生成场景 PoC
- BAGEL 多模态 API 设计与资源消耗评估
- 高并发和低预算降级策略设计

---

## 9. 当前限制

当前项目仍处于早期阶段，存在以下限制：

- 当前后端是 mock backend，不代表真实模型生成性能
- 当前 benchmark 尚未统计 P50 / P95
- 当前没有真实 GPU memory 数据
- 当前没有接入 Transformers / vLLM
- 当前没有并发压测
- 当前没有量化实验
- 当前没有 Prometheus / Grafana
- 当前没有 Docker 部署

这些限制会在后续阶段逐步补齐。

---

## 10. 求职价值对应关系

本项目最终希望覆盖 AI 推理 / AI Infra 岗位中的以下能力点：

| 岗位能力 | 项目对应模块 |
|---|---|
| LLM 服务化 | FastAPI `/generate` 接口 |
| 推理后端封装 | `app/backends/` |
| 推理预算控制 | `thinking_budget` 参数 |
| 性能测试 | `scripts/benchmark.py` |
| 延迟分析 | `client_latency_seconds` / `server_latency_seconds` |
| P50/P95 | 后续 benchmark 扩展 |
| 并发压测 | `benchmark_concurrency.py` |
| GPU 实验 | `gpu_smoke_test.py` / CX3 |
| vLLM serving | `vllm_backend.py` |
| 量化实验 | 后续 INT8 / 4bit 对比 |
| KV Cache 分析 | 后续长上下文实验 |
| 可观测性 | `app/metrics/` |
| 部署能力 | `deployment/` |
| 技术文档 | `docs/` |

---

## 11. 当前状态总结

当前已经完成：

```text
FastAPI 服务骨架
MockBackend
Thinking Budget 参数传递
Benchmark CSV 结果保存
Thinking Budget 实验说明文档
GitHub 版本管理
基础工程目录重构
```

下一步核心任务：

```text
接入 Transformers 小模型后端，让项目从 mock 推理升级为真实模型推理。
```

## Week2 RunPod Seed-OSS-36B Performance Evidence

This repository includes a reproducible Week2 performance study for `ByteDance-Seed/Seed-OSS-36B-Instruct` deployed with FastAPI + VLLMBackend + vLLM on RunPod 2×A100-SXM4-80GB.

Key results:

- Serving stack: FastAPI + VLLMBackend + vLLM 0.11.2
- Model: `ByteDance-Seed/Seed-OSS-36B-Instruct`
- Precision: BF16
- Tensor parallel size: 2
- Long-context serving config: `max_model_len=65536`
- Verified context levels: 8K, 16K, 32K, 56K, and 61.9K input tokens
- Concurrency benchmark: 1 / 2 / 4 / 8 / 16 concurrent requests
- Evidence preserved: logs, CSVs, metrics snapshots, nvidia-smi outputs, figures, and compressed artifacts

Important reports and evidence:

| Item | Path |
|---|---|
| Week2 performance report | `docs/week2_performance_optimization_report.md` |
| Long-context summary | `docs/week2_context_gradient_summary.md` |
| Prefix Cache investigation | `docs/week2_prefix_cache_investigation_summary.md` |
| RunPod 64K evidence | `evidence/week2_64k_context/` |
| Pre-32K evidence | `evidence/week2_pre_32k/` |
| Evidence archives | `artifacts/` |
| Performance figures | `figures/` |

Engineering interpretation:

- Concurrency testing shows QPS improves as concurrency increases from 1 to 16, while P50/P95 latency rises moderately and error rate remains 0.
- First-pass long-context testing shows latency increases and output tokens/s decreases as input tokens grow from 7.4K to 56.3K, matching expected prefill cost growth.
- The 61.9K near-limit result is treated separately because repeated long-document prompts are affected by vLLM prefix cache and warm state.
