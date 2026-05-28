# Week2 Seed-OSS-36B FP32 启动可行性边界记录

## 1. 实验目的

本次实验用于验证 Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 环境下使用 FP32 精度启动的资源边界，并与此前 BF16 成功部署结果形成对照。

该实验不以获得稳定线上推理服务为唯一目标，而是用于明确大模型推理服务中不同 dtype 对显存占用、加载时间、服务可用性和工程配置选择的影响。

## 2. 实验环境

- GPU：2×NVIDIA A100-SXM4-80GB
- CUDA Driver：580.126.16
- Python：3.11.10
- vLLM：0.11.2
- torch：2.9.0+cu128
- transformers：4.57.6
- 模型：ByteDance-Seed/Seed-OSS-36B-Instruct
- 模型缓存目录：/workspace/hf_cache
- 启动目录：/root/ai-inference-service

## 3. 启动配置

本次使用 vLLM OpenAI-compatible API server 启动 Seed-OSS-36B-Instruct，并显式设置 dtype=float32。

核心参数如下：

    python -m vllm.entrypoints.openai.api_server \
      --model ByteDance-Seed/Seed-OSS-36B-Instruct \
      --served-model-name ByteDance-Seed/Seed-OSS-36B-Instruct \
      --host 0.0.0.0 \
      --port 8002 \
      --tensor-parallel-size 2 \
      --distributed-executor-backend mp \
      --dtype float32 \
      --max-model-len 1024 \
      --max-num-batched-tokens 1024 \
      --max-num-seqs 1 \
      --gpu-memory-utilization 0.98 \
      --download-dir /workspace/hf_cache \
      --trust-remote-code \
      --enforce-eager

该配置已经将上下文长度、batch token budget 和并发序列数压到较保守水平，因此实验重点是 FP32 权重加载本身的资源边界，而不是高并发 serving 性能。

## 4. 关键观察

### 4.1 模型缓存

Stop/Start 前后，/workspace/hf_cache 保留成功，大小约 68GB，说明模型权重缓存位于持久化 volume 中，没有因容器重启丢失。

### 4.2 运行环境

Stop/Start 后，/root 容器环境被重置，vLLM、transformers 等 Python 包丢失，需要重新安装；但 /workspace/hf_cache 中模型缓存保留。

重新安装后环境恢复为：

- torch：2.9.0+cu128
- transformers：4.57.6
- vLLM：0.11.2
- CUDA available：True
- GPU count：2

### 4.3 FP32 显存占用

FP32 启动过程中，vLLM worker 进程在两张 A100 上均占用约 70890MiB 显存：

- GPU0：约 70899MiB / 81920MiB
- GPU1：约 70899MiB / 81920MiB

这说明即使在 TP=2、max_model_len=1024、max_num_seqs=1 的保守配置下，FP32 加载 Seed-OSS-36B 仍然接近单卡显存上限。

### 4.4 服务 ready 状态

在多次 /v1/models 探测中，API 未返回 ready 结果。日志显示模型完成下载后开始加载 safetensors checkpoint shards，但在后续过程中由于 Pod 被 Stop/Start，中断了完整加载验证。

因此本次不能记录为“FP32 成功服务化”，只能记录为“FP32 在 2×A100 80GB 下进入近满显存加载阶段，但未形成可用 API 服务”。

## 5. 与 BF16 成功实验的对比

此前 BF16 配置下，Seed-OSS-36B-Instruct 已在 2×A100-SXM4-80GB 上完成成功部署，并完成 FastAPI + vLLM 后端的端到端 smoke test、thinking budget 请求、benchmark 和 metrics 采集。

| 项目 | BF16 | FP32 |
|---|---:|---:|
| 2×A100 80GB 启动可行性 | 已成功 | 未完成 ready |
| API 服务可用性 | /v1/models 与 /generate 可用 | /v1/models 未 ready |
| 显存压力 | 高，但可运行 | 极高，接近显存边界 |
| 工程推荐程度 | 推荐 | 不推荐 |
| 适用场景 | 大模型推理服务主配置 | 资源边界对照 |

## 6. 工程结论

1. Seed-OSS-36B-Instruct 在 2×A100-SXM4-80GB 上更合理的服务化配置是 BF16，而不是 FP32。
2. FP32 对 36B 级模型的显存压力过高，即使将 max_model_len 降到 1024、max_num_seqs 降到 1，也没有形成稳定 API ready 证据。
3. 本次 FP32 实验的价值不在于性能提升，而在于证明 dtype 选择是大模型推理服务部署中的关键工程约束。
4. 后续性能优化应优先围绕 BF16 基线开展，包括 batch token tuning、KV cache、prefix cache、并发吞吐、P95 latency、Prometheus/Grafana 监控和 workload-aware serving profile，而不是继续消耗资源追求 FP32 serving。

## 7. 可写入报告的结论表达

在 Seed-OSS-36B-Instruct 的部署实验中，项目对 BF16 与 FP32 两种 dtype 的资源边界进行了对照验证。BF16 配置已在 2×A100-SXM4-80GB 上完成可用服务部署，并支持 FastAPI 到 vLLM 的端到端推理调用；FP32 配置在 TP=2、max_model_len=1024、max_num_seqs=1 的保守条件下仍占用约 70.9GB/GPU 显存，且未形成稳定 API ready 证据。该结果表明，对于 36B 级大模型推理服务，BF16 是更合理的工程部署选择，FP32 更适合作为资源边界分析和可行性对照，而不适合作为实际 serving 配置。
