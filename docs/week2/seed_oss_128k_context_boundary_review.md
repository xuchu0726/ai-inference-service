# Seed-OSS-36B-Instruct 128K 长上下文边界实验复盘

## 1. 实验目标

本实验用于验证 Seed-OSS-36B-Instruct 在 vLLM 128K serving profile 下的长上下文服务能力、边界行为和资源压力。

核心问题包括：

1. 服务是否能够以 `max_model_len=131072` 成功启动。
2. 单请求是否能够处理接近 128K tokens 的输入。
3. 请求超过上下文上限时，系统是否能够返回明确错误，而不是 OOM 或进程崩溃。
4. GPU 显存、KV cache、prefix cache、TTFT 和吞吐指标如何变化。

## 2. 服务配置

实验服务运行在 2×A100-SXM4-80GB 上，使用 vLLM OpenAI-compatible API。

关键参数如下：

| 配置项 | 数值 |
|---|---|
| model | ByteDance-Seed/Seed-OSS-36B-Instruct |
| served_model_name | Seed-OSS-36B-Instruct-128K |
| tensor_parallel_size | 2 |
| dtype | bfloat16 |
| max_model_len | 131072 |
| max_num_batched_tokens | 8192 |
| max_num_seqs | 1 |
| gpu_memory_utilization | 0.90 |
| download_dir | /workspace/hf_cache |

启动成功后，vLLM 日志显示：

| 指标 | 数值 |
|---|---:|
| Model loading memory | 33.7942 GiB |
| Available KV cache memory | 35.99 GiB |
| GPU KV cache size | 294,816 tokens |
| Maximum concurrency for 131,072 tokens/request | 2.25x |
| GPU memory after startup | ~73.7 GiB / 80 GiB per GPU |

## 3. 实验结果汇总

| Case | target_chars | input_tokens | status_code | ok | latency_seconds | output_tokens | tokens/s | 结论 |
|---|---:|---:|---:|---|---:|---:|---:|---|
| 128K conservative | 230000 | 126222 | 200 | True | 84.350549 | 128 | 1.5175 | 成功处理接近 128K 的长上下文请求 |
| 128K near-limit | 238000 | 130608 | 200 | True | 10.089885 | 128 | 12.686 | 成功逼近 131072 token 上限 |
| 128K over-limit | 246000 | 134991 | 400 | False | 0.19103 | 0 | 0.0 | 超过上下文上限后被 vLLM 明确拒绝 |

## 4. 关键观察

### 4.1 128K profile 启动成功

vLLM 在 `max_model_len=131072`、TP=2、BF16、`max_num_seqs=1` 下成功启动，没有出现 CUDA OOM。  
这说明 2×A100 80GB 可以支撑 Seed-OSS-36B-Instruct 的 128K 单请求边界验证，但显存余量已经不大，不适合直接扩大并发。

### 4.2 conservative 请求延迟明显高于 near-limit 请求

conservative case 输入 126222 tokens，client latency 为 84.35s。  
near-limit case 输入 130608 tokens，client latency 只有 10.09s。

该现象不能直接解释为 near-limit 更快，而应结合 prefix cache 理解：

- conservative 是第一次大长上下文请求，prefix cache hits 为 0；
- near-limit 与 conservative 使用高度重复的合同文本模板；
- near-limit 前后 metrics 显示 prefix cache hits 增加到 126208 tokens；
- 因此前后请求并非完全独立冷启动测试，near-limit 受到了 prefix cache 加速。

因此，near-limit 的 10.09s 不作为普通冷启动 128K 性能结论，而是作为热 prefix cache 场景下的边界通过证据。

### 4.3 over-limit 失败是有效边界证据

over-limit 请求包含 134991 input tokens，超过 `max_model_len=131072`。  
vLLM 在 preprocessing/tokenization 阶段返回 400 BadRequestError：

`This model's maximum context length is 131072 tokens. However, your request has 134991 input tokens.`

该请求没有进入 GPU 推理阶段，没有触发 OOM，也没有导致服务崩溃。  
这说明系统边界校验行为明确，超限请求可以安全失败。

### 4.4 KV cache 与显存压力

128K profile 启动后单卡显存约 73.7 GiB。长上下文请求后显存约 74.8 GiB。  
vLLM 日志显示 131072 tokens/request 的最大并发估计为 2.25x。  
这意味着 128K 长上下文 profile 的核心价值是验证长上下文能力，不适合承担高并发吞吐 profile。生产中应拆成不同 serving profile：

- short-context/high-throughput profile
- medium-context/mixed workload profile
- long-context/boundary profile

## 5. 文件保存状态

### 已原始提交

| 文件 | 说明 |
|---|---|
| logs/new_2xa100_seed_oss_128k_prelaunch_snapshot_20260529.txt | 128K 启动前环境、GPU、Git 状态 |
| logs/new_2xa100_seed_oss_128k_ready_check_20260529.txt | 128K 服务 ready 检查 |
| logs/new_2xa100_seed_oss_128k_vllm_launch_20260529.log | vLLM 128K 启动和运行日志 |
| logs/new_2xa100_seed_oss_128k_conservative_context_test_20260529.log | conservative 请求日志 |
| logs/new_2xa100_seed_oss_128k_near_limit_context_test_20260529.log | near-limit 请求日志 |
| results/new_2xa100_seed_oss_128k_conservative_context_test_20260529.csv | conservative 请求 CSV |
| results/new_2xa100_seed_oss_128k_near_limit_context_test_20260529.csv | near-limit 请求 CSV |

### 从终端记录恢复

| 文件 | 说明 |
|---|---|
| logs/new_2xa100_seed_oss_128k_over_limit_context_test_20260529_recovered.log | 根据终端记录恢复的 over-limit 关键日志 |
| results/new_2xa100_seed_oss_128k_over_limit_context_test_20260529.csv | 根据终端记录恢复的 over-limit CSV |

## 6. 路径事故复盘

旧实验发生在旧容器：

`root@ef0a0158d2cd:/root/ai-inference-service`

后续重新连接进入了新容器：

`root@20daa292f023`

新容器中 `/root/ai-inference-service` 不存在，`find / -name ai-inference-service` 也没有找到旧仓库。  
但是 `/workspace/hf_cache` 和 `/workspace/quantized_models` 仍然存在，说明模型缓存和量化 checkpoint 保存在持久化 workspace 中，而旧仓库和部分未 push 文件在容器本地层中。

结论：

1. 代码仓库和 evidence 不应放在 `/root` 作为唯一副本。
2. 实验产生的重要文件必须及时 push 到 GitHub。
3. 大模型缓存和大 checkpoint 可以继续放在 `/workspace`，但实验日志、CSV、报告、脚本必须进入 Git 仓库。
4. 如果必须在 `/root` 操作，完成一个实验阶段后必须立即提交并 push。

## 7. 后续使用方式

该 128K 实验可用于支撑以下结论：

1. Seed-OSS-36B-Instruct 可在 2×A100 80GB 上以 vLLM TP=2 启动 128K serving profile。
2. 130608 input tokens 的 near-limit 请求可以成功返回。
3. 超过 131072 token 的请求会被明确拒绝，系统安全失败，没有 OOM。
4. 128K profile 更适合长上下文边界验证，不适合作为高并发吞吐 profile。
5. prefix cache 会显著影响重复长文本请求的延迟，性能结论必须区分 cold prefix 和 warm prefix。
