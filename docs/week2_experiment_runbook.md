# Week2 实验运行手册：Seed-OSS-36B 性能优化与模型特性验证

## 1. 文档目的

本文档记录 Week2 GPU 实验的推荐执行顺序，用于保证 Seed-OSS-36B-Instruct 推理服务的并发测试、长上下文测试、监控采样、量化评估、数学推理和代码生成验证能够按统一流程完成。

本手册用于开 GPU 后直接执行，避免临时手工整理命令导致数据遗漏。

---

## 2. 实验前检查

开始实验前必须确认：

1. 当前分支为 `main`；
2. 本地代码已同步 GitHub；
3. `git status --short` 中没有未提交代码文件；
4. vLLM 服务端口使用 `8002`；
5. FastAPI 服务端口使用 `8000`;
6. `logs/`、`results/`、`figures/` 目录存在；
7. GPU 可见，`nvidia-smi` 正常；
8. vLLM `/v1/models` 可访问；
9. FastAPI `/health` 可访问；
10. FastAPI `/metrics` 和 vLLM `/metrics` 可访问。

---

## 3. 启动 Seed-OSS-36B vLLM 服务

使用 Week1 已验证的基础配置：

    VLLM_PORT=8002
    TENSOR_PARALLEL_SIZE=2
    MAX_MODEL_LEN=4096
    MAX_NUM_BATCHED_TOKENS=8192
    GPU_MEMORY_UTILIZATION=0.90
    DTYPE=bfloat16

启动脚本：

    bash deployment/cloud/run_vllm_seed_oss_36b_tp2.sh

验证：

    curl http://127.0.0.1:8002/v1/models

---

## 4. 启动 FastAPI 服务

设置 FastAPI 连接 vLLM：

    export INFERENCE_BACKEND=vllm
    export MODEL_NAME=ByteDance-Seed/Seed-OSS-36B-Instruct
    export VLLM_MODEL_NAME=ByteDance-Seed/Seed-OSS-36B-Instruct
    export VLLM_BASE_URL=http://127.0.0.1:8002/v1
    export VLLM_ENABLE_SEED_THINKING_BUDGET=true
    export VLLM_TIMEOUT_SECONDS=900

启动：

    bash deployment/cloud/run_fastapi_vllm.sh

验证：

    curl http://127.0.0.1:8000/health
    curl http://127.0.0.1:8000/metrics

---

## 5. 启动 GPU 采样

在单独终端中运行：

    bash scripts/sample_gpu_metrics.sh logs/week2_nvidia_smi_sampling.csv 5

该脚本会持续记录 GPU 显存、GPU utilization 和 memory utilization。

---

## 6. Smoke Test

先运行基础 smoke test，确认服务链路可用：

    python deployment/cloud/smoke_test_generate.py

保存输出到 `results/`，并记录一次 vLLM metrics 快照：

    python scripts/snapshot_vllm_metrics.py \
      --url http://127.0.0.1:8002/metrics \
      --output results/week2_vllm_metrics_snapshot_before_benchmark.txt

---

## 7. 并发性能测试

运行并发矩阵：

    CONCURRENCY_VALUES="1 2 4 8 16" \
    THINKING_BUDGETS="512" \
    REPEAT=2 \
    MAX_NEW_TOKENS=128 \
    bash scripts/run_week2_concurrency_matrix.sh

主要输出：

    results/week2_concurrency_c1.csv
    results/week2_concurrency_c2.csv
    results/week2_concurrency_c4.csv
    results/week2_concurrency_c8.csv
    results/week2_concurrency_c16.csv

    results/week2_concurrency_c1_summary.csv
    results/week2_concurrency_c2_summary.csv
    results/week2_concurrency_c4_summary.csv
    results/week2_concurrency_c8_summary.csv
    results/week2_concurrency_c16_summary.csv

并发测试后记录 vLLM metrics：

    python scripts/snapshot_vllm_metrics.py \
      --url http://127.0.0.1:8002/metrics \
      --output results/week2_vllm_metrics_snapshot_after_concurrency.txt

---

## 8. 长上下文梯度测试

先从 4K/8K/16K/32K 开始：

    python scripts/benchmark_context_length.py \
      --url http://127.0.0.1:8000/generate \
      --output results/week2_context_length_benchmark.csv \
      --context-targets 4k,8k,16k,32k \
      --max-new-tokens 256 \
      --thinking-budget 512 \
      --timeout-seconds 1800

如 32K 稳定，再尝试 64K：

    python scripts/benchmark_context_length.py \
      --url http://127.0.0.1:8000/generate \
      --output results/week2_context_length_benchmark_64k.csv \
      --context-targets 64k \
      --max-new-tokens 256 \
      --thinking-budget 512 \
      --timeout-seconds 2400

长上下文测试后记录 vLLM metrics：

    python scripts/snapshot_vllm_metrics.py \
      --url http://127.0.0.1:8002/metrics \
      --output results/week2_vllm_metrics_snapshot_after_context.txt

---

## 9. 数学推理与代码生成验证

运行 GSM8K-style 和代码生成小样本：

    python scripts/eval_week2_reasoning_codegen.py \
      --url http://127.0.0.1:8000/generate \
      --output results/week2_reasoning_codegen_eval.csv \
      --mode all \
      --max-new-tokens 256 \
      --thinking-budget 512 \
      --timeout-seconds 900

输出用于验证 Seed-OSS-36B 在数学推理和代码生成场景下的基础能力。

---

## 10. 量化实验记录原则

Week2 实际 baseline 使用 BF16。

若尝试 FP32、INT8、FP8、AWQ 或 GPTQ，需要保存：

1. 启动命令；
2. vLLM 日志；
3. nvidia-smi 输出；
4. benchmark CSV；
5. summary CSV；
6. OOM / timeout / compatibility error；
7. 显存、P95、QPS、tokens/s 和输出质量观察。

如果 FP32 或 INT8 无法在当前资源下运行，不能删除失败记录，应在报告中说明资源边界和替代方案。

---

## 11. 生成图表

实验结束后运行：

    python scripts/plot_week2_results.py \
      --results-dir results \
      --figures-dir figures

预期生成：

1. QPS vs concurrency；
2. P50 latency vs concurrency；
3. P95 latency vs concurrency；
4. tokens/s vs concurrency；
5. error_rate vs concurrency；
6. latency vs context length；
7. tokens/s vs context length；
8. success vs context length。

---

## 12. 最终整理

实验完成后需要提交：

1. `results/week2_*.csv`
2. `logs/week2_*.log`
3. `logs/week2_nvidia_smi_sampling.csv`
4. `figures/week2_*.png`
5. 更新后的 `docs/week2_performance_optimization_report.md`

报告必须覆盖：

1. 并发性能；
2. Batch / dynamic batching 行为；
3. 长上下文资源边界；
4. KV Cache / GQA / PagedAttention；
5. 量化可行性；
6. 数学推理；
7. 代码生成；
8. 监控与 GPU 瓶颈；
9. 未完成项和资源限制。
