# Week2 Seed-OSS-36B FP32 启动尝试记录

## 1. 实验目的

本次实验用于尝试在 2×NVIDIA A100-SXM4-80GB 环境下，以 FP32 精度启动 Seed-OSS-36B-Instruct，并观察其模型加载过程、显存占用和服务 ready 状态。

需要明确的是：本次实验原始目标是验证 FP32 serving 是否能够形成可用 API 服务，而不是一开始就设计为完整的边界测试。由于实验过程中 Pod 被 Stop/Start，中断了完整加载流程，因此本记录不作为 FP32 可行性最终结论，只作为一次 FP32 启动尝试和部分资源占用证据。

## 2. 实验环境

| 项目 | 配置 |
|---|---|
| GPU | 2×NVIDIA A100-SXM4-80GB |
| CUDA Driver | 580.126.16 |
| Python | 3.11.10 |
| vLLM | 0.11.2 |
| torch | 2.9.0+cu128 |
| transformers | 4.57.6 |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 模型缓存目录 | /workspace/hf_cache |
| 项目目录 | /root/ai-inference-service |

## 3. 启动配置

本次通过 vLLM OpenAI-compatible API server 启动模型，并显式设置 dtype=float32。

核心启动参数如下：

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

本次配置已经尽量降低 FP32 启动压力：

| 参数 | 设置 | 目的 |
|---|---:|---|
| tensor_parallel_size | 2 | 使用两张 A100 分摊模型权重 |
| dtype | float32 | 验证 FP32 资源压力 |
| max_model_len | 1024 | 降低 KV cache 压力 |
| max_num_batched_tokens | 1024 | 降低批处理 token budget |
| max_num_seqs | 1 | 降低并发序列数量 |
| gpu_memory_utilization | 0.98 | 尽量提高可用显存比例 |
| enforce_eager | enabled | 降低 CUDA graph 相关不确定性 |

## 4. 已观察到的结果

### 4.1 环境恢复结果

Stop/Start 后，容器环境被重置，重新安装 vLLM 0.11.2 后验证成功。

环境检查结果如下：

| 项目 | 结果 |
|---|---|
| torch | 2.9.0+cu128 |
| transformers | 4.57.6 |
| vLLM | 0.11.2 |
| CUDA available | True |
| GPU count | 2 |
| GPU0 | NVIDIA A100-SXM4-80GB |
| GPU1 | NVIDIA A100-SXM4-80GB |

### 4.2 模型缓存结果

模型缓存目录 `/workspace/hf_cache` 保留成功，大小约 68GB。

这说明 RunPod Stop/Start 后，`/root` 中的代码和 Python 环境会被重置，但 `/workspace/hf_cache` 中的模型缓存仍然保留。因此后续重新启动 FP32 时，不需要重新下载完整模型权重，只需要恢复项目代码和 Python/vLLM 环境。

### 4.3 FP32 显存占用

FP32 启动过程中，vLLM worker 进程在两张 A100 上均占用约 70890MiB 显存。

| GPU | 显存占用 |
|---|---:|
| GPU0 | 约 70899MiB / 81920MiB |
| GPU1 | 约 70899MiB / 81920MiB |

这说明 FP32 配置在 2×A100 80GB 上显存压力很高。  
但当前证据不足以证明 FP32 最终一定不能 ready。

### 4.4 模型加载进度

日志显示模型完成下载后开始加载 safetensors checkpoint shards。

关键日志包括：

    Time spent downloading weights for ByteDance-Seed/Seed-OSS-36B-Instruct: 1120.171463 seconds
    Loading safetensors checkpoint shards: 0/15
    Loading safetensors checkpoint shards: 1/15
    Loading safetensors checkpoint shards: 2/15

但是在 safetensors shard 加载过程中，Pod 被 Stop/Start，导致完整加载流程被中断。

### 4.5 API ready 状态

在多次 `/v1/models` 探测中，API 未返回 ready 结果。  
由于实验被中断，本次没有得到最终的 API ready、OOM、进程退出或明确错误日志。

因此，本次不能记录为 FP32 成功服务化，也不能记录为 FP32 明确失败。

## 5. 当前结论

本次实验只能得出以下谨慎结论：

1. Seed-OSS-36B-Instruct FP32 启动可以进入 vLLM 初始化和模型加载阶段。
2. FP32 加载阶段在 2×A100-SXM4-80GB 上观察到约 70.9GB/GPU 的高显存占用。
3. 模型权重缓存已保留在 `/workspace/hf_cache`，后续重启实验不需要重新下载完整权重。
4. 当前实验由于 Pod 被 Stop/Start 中断，未完成最终可用性验证。
5. 当前证据不能证明 FP32 在 2×A100 80GB 下不可行，也不能证明 FP32 可以稳定服务化。
6. 后续必须重新启动 FP32，并等待完整结果后，才能形成正式工程结论。

## 6. 与 BF16 实验的关系

此前 BF16 配置下，Seed-OSS-36B-Instruct 已经在 2×A100-SXM4-80GB 上完成成功部署，并完成 FastAPI + vLLM 后端的端到端 smoke test、thinking budget 请求、benchmark 和 metrics 采集。

因此，当前已确认的事实是：

| 项目 | BF16 | FP32 |
|---|---|---|
| 2×A100 80GB 服务化 | 已成功 | 尚未验证完成 |
| API ready | 已完成 | 未完成 |
| FastAPI E2E | 已完成 | 未完成 |
| benchmark | 已完成 | 未完成 |
| 显存压力 | 高，但可运行 | 已观察到极高显存占用 |
| 当前工程结论 | 可作为主部署配置 | 需要继续补测 |

## 7. 后续补测目标

下一次 FP32 补测需要完成以下判断：

1. 是否能完整加载 15 个 safetensors checkpoint shards；
2. 是否能返回 `/v1/models`；
3. 是否能完成一次最小 chat completion；
4. 是否出现 CUDA OOM、worker 退出、进程异常、API server 不可用或长时间无进展；
5. 如果成功 ready，需要记录显存、启动耗时、KV cache、最小请求 latency 和输出结果；
6. 如果失败，需要保留完整日志、GPU snapshot、进程状态和失败原因。

## 8. 后续判定标准

| 观察结果 | 判定 |
|---|---|
| `/v1/models` 返回模型信息 | FP32 ready，可以继续 smoke test |
| 出现 CUDA out of memory | FP32 在当前配置下失败 |
| 进程退出且日志有异常 | 记录失败原因 |
| 长时间无日志推进且 API 不 ready | 记录为长时间未 ready，不直接写不可行 |
| 成功 ready 但显存接近上限 | 继续最小 generation，并记录性能和显存 |

## 9. 可写入报告的谨慎表达

本阶段曾尝试在 2×A100-SXM4-80GB 环境下以 FP32 精度启动 Seed-OSS-36B-Instruct。实验过程中，模型成功进入 vLLM 初始化和 safetensors checkpoint shard 加载阶段，并观察到约 70.9GB/GPU 的高显存占用。但由于 Pod Stop/Start 中断了完整加载流程，本次未形成 API ready 或明确失败证据。因此，该实验仅作为 FP32 启动尝试和显存压力观察记录，不作为 FP32 可行性最终结论。后续仍需重新运行 FP32 配置，并基于完整 ready、OOM、进程退出或长时间未响应结果形成最终判断。
