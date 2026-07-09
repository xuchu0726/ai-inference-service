# AI Inference Service

## 0. 最终交付状态

本仓库当前最终交付分支为 `feature/week4-redis-shared-resilience`。Week4 已补齐压测验收、真实主备验证、Redis shared circuit breaker、controlled CUDA-OOM fault injection、长文本 / 代码生成 / BAGEL 图文推理 E2E 验证、Triton RMSNorm-INT8 A100 microbenchmark，以及最终交付文档。

最终交付入口：

| 目的 | 文档 |
|---|---|
| Week4 最终交付主报告 | `docs/week4_final_delivery_report.md` |
| Week4 最终系统验证矩阵 | `docs/week4_system_validation_matrix.md` |
| Week3 阶段交付报告 | `docs/week3_delivery_report.md` |
| Week3 要求闭环附录 | `docs/week3_requirement_closure.md` |

重要边界：

1. 1000 QPS、P95≤500ms、错误率≤1% 指 `/jobs` admission 场景，不代表 Seed-OSS-36B 完整生成达到 1000 QPS。
2. 512K 长上下文来自历史 4×A100 profile 的 500K+ token 近上限验证；Week4 TP=2 主备 profile 用于主备、压测、队列和容错验证。
3. OOM 验证为 controlled CUDA-OOM fault injection；节点故障验证为主推理 upstream 受控终止与恢复。
4. FlashAttention 是 vLLM runtime 自动选择并实际启用的 backend；Triton RMSNorm-INT8 是独立 microkernel 验证。


本项目是一个面向大模型推理服务、LLM Serving 和 AI Infra 场景的工程化推理系统。项目目标不是实现简单聊天机器人 demo，而是围绕真实大模型部署、API 服务化、vLLM serving、性能测试、长上下文验证、量化对比、Batch 调优和可观测性分析，构建一套可运行、可压测、可复现、可解释的推理服务实验平台。

当前核心链路：

    Client / Benchmark Script
      -> FastAPI /generate
      -> VLLMBackend
      -> vLLM OpenAI-Compatible Server
      -> ByteDance-Seed/Seed-OSS-36B-Instruct
      -> 2 x NVIDIA A100-SXM4-80GB GPU inference

## 1. 核心进展

当前项目已经完成以下关键能力：

1. 基于 FastAPI 实现 /health、/generate 和 /metrics 接口。
2. 实现可插拔推理后端，包括 MockBackend、TransformersBackend 和 VLLMBackend。
3. 完成 ByteDance-Seed/Seed-OSS-36B-Instruct 在 2 x NVIDIA A100-SXM4-80GB 上的 vLLM tensor parallel 部署。
4. 完成 FastAPI + VLLMBackend + vLLM + Seed-OSS-36B-Instruct 端到端推理链路。
5. 接入 Thinking Budget 参数链路。
6. 完成 P50/P95 latency、QPS、tokens/s、error rate 等 benchmark 指标采集。
7. 完成 concurrency = 1 / 2 / 4 / 8 / 16 的并发测试。
8. 完成 64K 级别长上下文梯度测试。
9. 完成 128K serving profile 边界验证。
10. 完成 Prefix Cache 行为分析。
11. 完成 max_num_batched_tokens batch-token 调优实验。
12. 完成 FP32 baseline 与 W8A8 compressed-tensors 量化 serving 对比。
13. 完成 GSM8K full benchmark。
14. 完成代码生成 mini eval。
15. 接入 FastAPI metrics、vLLM metrics、Prometheus 配置和 Grafana dashboard evidence。
16. 保存原始日志、CSV、metrics、nvidia-smi、图表和 evidence 压缩包，用于复现和审计。

## 2. 当前主要实验结果

### 2.1 Seed-OSS-36B 基础部署

| 项目 | 结果 |
|---|---|
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理框架 | vLLM 0.11.2 |
| GPU | 2 x NVIDIA A100-SXM4-80GB |
| Tensor Parallel | TP=2 |
| 精度 | BF16 |
| API 服务 | FastAPI + VLLMBackend |
| 服务状态 | 已完成端到端验证 |

### 2.2 并发测试

在固定 128 output tokens 条件下，concurrency 从 1 提升到 16：

| 指标 | 结果 |
|---|---|
| QPS | 0.325 -> 3.848 |
| 吞吐提升 | 约 11.84x |
| P95 latency | 3.348s -> 3.532s |
| error rate | 0 |

结论：vLLM continuous batching 能显著提升吞吐，同时保持可控的尾延迟增长。

### 2.3 长上下文测试

64K serving profile 下的长上下文梯度测试：

| Context | Input tokens | Client latency | Status |
|---|---:|---:|---|
| 8K | 7,434 | 4.811523s | success |
| 16K | 15,297 | 5.439229s | success |
| 32K | 30,465 | 8.570771s | success |
| 56K | 56,303 | 16.128279s | success |
| 61.9K | 61,917 | 7.437081s | success, cache-affected |

128K serving profile 边界验证：

| Case | Input tokens | Status | Latency |
|---|---:|---|---:|
| 128K conservative | 126,222 | success | 84.350549s |
| 128K near-limit | 130,608 | success, cache-affected | 10.089885s |
| 128K over-limit | 134,991 | rejected by vLLM | 0.191030s |

512K 长上下文已在历史 4×A100 profile 下完成 500K+ token 近上限验证；Week4 TP=2 主备 profile 用于主备、压测、队列和容错验证。

### 2.4 Batch-Token 调优

围绕 vLLM max_num_batched_tokens 完成专项实验。结论是该参数不存在全局最优值，应根据 workload 类型选择 serving profile。

| Workload | 结论 |
|---|---|
| short-output burst | 更适合 32768 profile |
| long-output / mixed workload | 更适合 8192 profile |

该结果已经沉淀为 workload-aware routing policy abstraction。

### 2.5 量化实验

当前稳定量化闭环是 FP32 baseline 与 W8A8 compressed-tensors serving 对比。

| 项目 | 结果 |
|---|---|
| FP32 baseline | 已完成 serving、smoke test 和 batch-profile benchmark |
| W8A8 compressed-tensors | 已完成离线量化、vLLM serving 和同参数对比 |
| QPS / tokens/s 提升 | 约 31.4% 到 126.1% |
| model loading memory | 约 67.59 GiB -> 17.71 GiB |
| 显存收益解释 | 权重加载显存下降，KV cache/concurrency headroom 增加 |
| 边界 | runtime nvidia-smi 总显存不会同比下降，因为 vLLM 会利用释放出的显存扩展 KV cache |

plain INT8 / AWQ / GPTQ 稳定 serving 尚未完成，相关尝试记录为兼容性边界；本阶段稳定闭环为 FP32 baseline 与 W8A8 compressed-tensors serving 对比。

### 2.6 GSM8K 与代码生成验证

GSM8K full benchmark：

| 指标 | 结果 |
|---|---:|
| 总样本数 | 1319 |
| API 成功样本数 | 1319 |
| API error rate | 0 |
| 正确样本数 | 999 |
| Accuracy | 75.74% |
| Client latency P50 | 5.51s |
| Client latency P95 | 6.69s |

代码生成 mini eval：

| 指标 | 结果 |
|---|---:|
| 总样本数 | 5 |
| API 成功样本数 | 5 |
| API 失败样本数 | 0 |
| 简单正确性检查 | 5 / 5 passed |

## 3. 项目结构

核心目录如下：

    ai-inference-service/
      app/
        main.py
        schemas.py
        config.py
        inference.py
        routing.py
        backends/
      scripts/
        benchmark_vllm_backend.py
        analyze_vllm_benchmark.py
        benchmark_context_length.py
        sample_gpu_metrics.sh
        snapshot_vllm_metrics.py
      deployment/
        cloud/
        monitoring/
      docs/
        week1_delivery_report.md
        week2_delivery_summary.md
        week2_performance_optimization_report.md
        week2_requirement_compliance_matrix.md
        week2_batch_token_tuning_report.md
        week2_quantization_feasibility_report.md
        week2_observability_report.md
        week2_eval_mini_report.md
        week2/
      results/
      logs/
      figures/
      evidence/
      artifacts/

## 4. 关键文档入口

建议阅读顺序：

| 目的 | 文档 |
|---|---|
| 快速了解 Week2 交付 | docs/week2_delivery_summary.md |
| 查看 Week2 主性能报告 | docs/week2_performance_optimization_report.md |
| 查看 Week2 验收映射 | docs/week2_requirement_compliance_matrix.md |
| 查看 Batch-Token 调优 | docs/week2_batch_token_tuning_report.md |
| 查看量化实验边界 | docs/week2_quantization_feasibility_report.md |
| 查看可观测性分析 | docs/week2_observability_report.md |
| 查看 GSM8K 与代码生成 | docs/week2_eval_mini_report.md |
| 查看 128K 长上下文边界实验 | docs/week2/seed_oss_128k_context_boundary_review.md |
| 查看 Week1 交付 | docs/week1_delivery_report.md |

## 5. 运行方式

安装基础依赖：

    pip install -r requirements.txt

安装 vLLM 依赖：

    pip install -r requirements-vllm.txt

启动 FastAPI：

    uvicorn app.main:app --host 0.0.0.0 --port 8000

云端 vLLM 后端启动 FastAPI：

    bash deployment/cloud/run_fastapi_vllm.sh

启动 Seed-OSS vLLM 服务：

    VLLM_PORT=8002 \
    TENSOR_PARALLEL_SIZE=2 \
    MAX_MODEL_LEN=65536 \
    MAX_NUM_BATCHED_TOKENS=8192 \
    GPU_MEMORY_UTILIZATION=0.90 \
    DTYPE=bfloat16 \
    bash deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

检查服务状态：

    curl http://127.0.0.1:8000/health
    curl http://127.0.0.1:8002/v1/models
    curl http://127.0.0.1:8000/metrics
    curl http://127.0.0.1:8002/metrics

## 6. API 示例

GET /health：

    curl http://127.0.0.1:8000/health

POST /generate：

    curl -X POST http://127.0.0.1:8000/generate \
      -H "Content-Type: application/json" \
      -d '{
        "prompt": "请用三句话解释什么是 KV Cache。",
        "max_new_tokens": 128,
        "temperature": 0.0,
        "thinking_budget": 512
      }'

核心返回字段包括：

    response
    latency_seconds
    input_tokens
    output_tokens
    tokens_per_second
    backend
    model_name
    device
    thinking_budget

## 7. Benchmark 与评测

vLLM backend benchmark：

    python scripts/benchmark_vllm_backend.py \
      --url http://127.0.0.1:8000/generate \
      --output results/benchmark.csv \
      --concurrency 4 \
      --repeat 10 \
      --max-new-tokens 128 \
      --temperature 0.0 \
      --thinking-budgets 512 \
      --timeout-seconds 600

生成 summary：

    python scripts/analyze_vllm_benchmark.py \
      --input results/benchmark.csv \
      --output results/benchmark_summary.csv

长上下文 benchmark：

    python scripts/benchmark_context_length.py \
      --url http://127.0.0.1:8000/generate \
      --output results/week2_context_length_benchmark.csv \
      --context-targets 8k,16k,32k,64k \
      --max-new-tokens 128 \
      --thinking-budget 512

## 8. 监控与证据保存

项目已保存以下类型 evidence：

1. vLLM 启动日志；
2. FastAPI 服务日志；
3. health、models、metrics 输出；
4. benchmark CSV；
5. summary CSV；
6. nvidia-smi snapshot；
7. nvidia-smi sampling；
8. Prometheus scrape 配置；
9. Grafana dashboard JSON 与截图；
10. 性能图表；
11. evidence 压缩包。

核心证据目录：

    results/
    logs/
    figures/
    evidence/
    artifacts/
    deployment/monitoring/

## 9. 当前边界

1. 512K 长上下文来自历史 4×A100 profile 的 500K+ token 近上限验证，不作为 Week4 TP=2 主备 profile 的常态 SLA。
2. plain INT8 / AWQ / GPTQ 稳定 serving 尚未完成。
3. FP8 KV cache 尚未完成。
4. 代码生成测试使用 Seed-OSS-36B-Instruct，不是 Seed-Coder 专项模型。
5. 128K near-limit latency 受 prefix cache / warm state 影响，不能代表 cold prompt 128K 性能。
6. W8A8 的显存收益以模型权重加载显存下降和 KV cache headroom 增加为主要口径；runtime nvidia-smi 总显存不作为同比下降结论。

## 10. 阶段结论

当前项目已经从早期 FastAPI demo 升级为真实大模型推理服务实验平台。

截至 Week2，项目已经形成以下闭环：

1. Seed-OSS-36B-Instruct 真实部署；
2. FastAPI + VLLMBackend + vLLM serving；
3. 多并发 benchmark；
4. 64K / 128K 长上下文验证；
5. Prefix Cache 分析；
6. Batch-token serving profile 调优；
7. FP32 vs W8A8 量化 serving 对比；
8. GSM8K full benchmark；
9. 代码生成 mini eval；
10. Prometheus / Grafana / nvidia-smi 可观测性证据；
11. 可复现文档、日志、CSV、图表和 evidence 归档。

下一阶段重点是高可用架构、降级策略、多实例 serving profile、压测、告警规则、多模态或代码模型专项验证。
