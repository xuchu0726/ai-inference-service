# Week2 Hardening 补充验证总结

## 1. 文档目的

本文档用于汇总 Week2 性能优化实验后的补充验证工作，重点说明长上下文推理、FP8 KV Cache、量化路径、代码生成验证、显存统计口径和 GSM8K 评测口径的补充结果。

本文档只记录已经完成的实验事实、当前证据和仍存在的边界，不对未实测内容作推断。

## 2. 512K 长上下文与 FP8 KV Cache 验证

### 2.1 BF16 KV 512K 配置验证

本次补充实验在 4×A100-SXM4-80GB 环境下，对 Seed-OSS-36B-Instruct 的 512K 长上下文 serving 配置进行了真机验证。

实验配置如下：

- 模型：`ByteDance-Seed/Seed-OSS-36B-Instruct`
- Serving engine：vLLM
- Tensor parallel size：4
- `max_model_len`：524288
- Model dtype：bfloat16
- API：OpenAI-compatible `/v1/chat/completions`

实测结果：

- vLLM 成功接受 `max_model_len=524288` 配置；
- 服务完成启动并进入 `Application startup complete` 状态；
- 约 500K prompt tokens 的 near-limit 请求成功返回；
- 实际 `prompt_tokens`：500,033；
- `total_tokens`：500,065；
- HTTP status：200；
- 端到端 latency：533.85s；
- 实验过程中未观察到 OOM、进程退出或 RuntimeError。

相关证据：

- `evidence/week2_hardening/seed_oss_4xa100_512k_ready_evidence_20260614.txt`
- `results/week2_hardening/seed_oss_4xa100_512k_near_limit_summary_20260614.json`
- `evidence/week2_hardening/seed_oss_4xa100_512k_near_limit_result_evidence_20260614.txt`

### 2.2 FP8 KV 512K 配置验证

在相同 4×A100 环境下，进一步验证了 `kv_cache_dtype=fp8` 的 512K serving 配置。

主要配置差异：

- `kv_cache_dtype=fp8`

实测结果：

- vLLM 成功接受 `max_model_len=524288` 与 `kv_cache_dtype=fp8` 配置；
- 服务完成启动并进入 `Application startup complete` 状态；
- vLLM 日志确认使用 FP8 数据类型存储 KV Cache；
- GPU KV cache size 从 BF16 KV 配置下的 909,360 tokens 提升到 1,807,008 tokens；
- 524,288-token request 的 theoretical concurrency 从 1.73x 提升到 3.45x；
- 约 500K prompt tokens 的 FP8 KV near-limit 请求成功返回；
- 实际 `prompt_tokens`：500,037；
- `total_tokens`：500,069；
- HTTP status：200；
- 端到端 latency：770.60s。

结果解释：

FP8 KV Cache 在本实验中明显提升了 KV Cache 容量和 512K 请求的并发余量。按 vLLM 日志计算，KV Cache 容量和 theoretical concurrency 约提升 1.99 倍。

但在单个 500K near-limit 请求中，FP8 KV 的 latency 高于 BF16 KV。因此，当前实验只能说明 FP8 KV 对长上下文容量和并发余量有明显帮助，不能表述为单请求 latency 优化。

相关证据：

- `evidence/week2_hardening/seed_oss_4xa100_512k_fp8kv_ready_evidence_20260614.txt`
- `results/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_summary_20260614.json`
- `evidence/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_result_evidence_20260614.txt`
- `evidence/week2_hardening/seed_oss_4xa100_512k_bf16_vs_fp8kv_summary_20260614.txt`

## 3. 量化路径与失败边界

当前项目已经完成 W8A8 compressed-tensors 路径的离线量化、vLLM serving、smoke test 和并发压测，但其他量化路径需要按实际结果区分。

### 3.1 已完成的 W8A8 路径

已完成内容包括：

- 离线生成 W8A8 compressed-tensors checkpoint；
- 使用 vLLM compressed-tensors 后端加载 W8A8 模型；
- 日志确认使用 `CompressedTensorsW8A8Int8 / CutlassScaledMMLinearKernel`；
- 完成 W8A8 smoke test；
- 完成 W8A8 concurrency sweep；
- 生成 FP32 与 W8A8 batch profile 对比结果。

相关证据：

- `logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt`
- `logs/new_2xa100_seed_oss_w8a8_ready_evidence_20260528.txt`
- `logs/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_summary_20260528.txt`
- `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`

### 3.2 严格 INT8 / compressed-tensors 直接 serving 失败边界

对原始 BF16 checkpoint 直接使用 compressed-tensors / strict INT8 类 serving 的尝试未能成功。日志显示，该路径需要预量化 checkpoint 中包含 compressed-tensors 后端所需的量化配置字段。

主要失败原因包括缺少：

- `target_scheme_map`
- `quant_format`
- `sparsity_scheme_map`
- 其他 compressed-tensors 配置字段

这说明原始 BF16 checkpoint 不能仅依靠运行时参数直接变成严格 INT8/W8A8 compressed-tensors serving；该路径需要预量化产物或完整离线量化流程。

相关证据：

- `logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt`
- `logs/new_2xa100_seed_oss_compressed_tensors_int8_vllm_launch_20260528.log`
- `logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt`

## 4. 代码生成验证补充

原有代码生成验证样本数量较少，因此本次补充了 50 个 HumanEval/MBPP-style 的轻量函数生成任务，并为每个任务设置本地 Python 单元测试。

实验配置：

- 模型：`ByteDance-Seed/Seed-OSS-36B-Instruct`
- Serving profile：512K FP8 KV
- GPU：4×A100-SXM4-80GB
- Tensor parallel size：4
- API：OpenAI-compatible `/v1/chat/completions`
- 验证方式：本地 Python 单元测试

需要说明的是，该评测不是官方 HumanEval 或 MBPP 完整 benchmark，只是轻量子集验证。

### 4.1 初版评测与修正

初版 20 题中，API 请求均返回 HTTP 200，但本地单元测试全部失败。检查结果显示，主要问题不是服务不可用，而是初版 prompt、generation budget 和代码提取逻辑对 Seed-OSS 输出格式控制不足，模型输出容易被 thinking tag 或非最终代码内容占用。

随后进行了修正版评测，调整包括：

- 增加 `max_tokens`；
- 使用更严格的 code-only system prompt；
- 增强代码块和函数定义提取逻辑；
- 保留每题原始输出、提取代码、错误信息和测试结果。

### 4.2 修正版 50 题结果

修正版 20 题结果：

- 题目数：20
- 通过：10
- 失败：10
- 通过率：50.0%
- 平均 latency：7.19s

追加 30 题结果：

- 题目数：30
- 通过：16
- 失败：14
- 通过率：53.3%
- 平均 latency：8.54s

合计 50 题结果：

- 题目数：50
- 通过：26
- 失败：24
- 通过率：52.0%
- 加权平均 latency：约 8.00s

结果解释：

当前服务能够稳定响应代码生成请求，并在部分轻量函数生成任务中生成可执行且通过单元测试的代码。但通过率不高，因此不应表述为完整代码生成能力评测，也不应与官方 HumanEval/MBPP 榜单结果直接比较。

更准确的结论是：当前实验完成了轻量代码生成验证，同时暴露出模型在 code-only 输出控制、thinking tag 处理、边界条件实现和自动评测适配方面仍有改进空间。

相关证据：

- `results/week2_hardening/seed_oss_codegen_eval_20_repair_summary_20260614.json`
- `results/week2_hardening/seed_oss_codegen_eval_additional_30_summary_20260615.json`
- `evidence/week2_hardening/seed_oss_codegen_eval_50_summary_20260615.txt`

## 5. 显存收益统计口径

W8A8 量化实验中的显存收益需要区分“模型加载显存”和“运行时总显存”。

当前应采用的口径如下：

- W8A8 明显降低模型权重加载阶段的显存占用；
- 模型加载显存从 67.59 GiB 降至 17.71 GiB；
- 对应降幅为 73.8%；
- 运行时 `nvidia-smi` 总显存没有按相同比例下降，因为 vLLM 会将释放出的显存用于扩展 KV Cache。

因此，后续文档中应写为：

> W8A8 compressed-tensors profile 将模型加载显存从 67.59 GiB 降至 17.71 GiB，降幅为 73.8%。

不应写为：

> 运行时 GPU 显存下降 73.8%。

相关证据：

- `logs/new_2xa100_seed_oss_fp32_vs_w8a8_quantization_summary_20260528.txt`
- `docs/week2_quantization_feasibility_report.md`
- `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`

## 6. GSM8K baseline 与 W8A8 精度缺口

当前仓库中已有完整 GSM8K baseline 结果：

- 文件：`results/week2_gsm8k_full_seed_oss_budget0.csv`
- 总题数：1319
- 正确题数：999
- accuracy：75.74%
- backend：vLLM
- `max_new_tokens`：256

该结果应解释为 Seed-OSS-36B-Instruct 在 vLLM serving 路径下的数学推理 baseline。它不能解释为 W8A8 量化模型的 accuracy。

本次补充进行了 GSM8K 与 W8A8 相关证据扫描。扫描结果显示，仓库中存在 W8A8 serving、W8A8 性能压测和 FP32 vs W8A8 性能对比证据，但未发现同时满足以下条件的结果文件：

- GSM8K 评测；
- W8A8 compressed-tensors serving profile；
- accuracy / correct / total 等精度字段。

当前 hardening 环境中也不存在此前生成的 W8A8 checkpoint：

- `/workspace/quantized_models` 不存在；
- `/workspace/quantized_models/Seed-OSS-36B-Instruct-W8A8` 不存在。

因此，W8A8 GSM8K accuracy 仍是未实测项，不能从 BF16/vLLM baseline 的 75.74% 推断。

处理原则：

- GSM8K 75.74% 只作为 BF16/vLLM baseline；
- W8A8 结果只用于 serving、吞吐、延迟、显存和并发能力分析；
- W8A8 精度损耗需要在恢复或重新生成 W8A8 checkpoint 后，用相同 GSM8K 脚本补测。

相关证据：

- `evidence/week2_hardening/gsm8k_w8a8_file_index_20260615.txt`
- `evidence/week2_hardening/gsm8k_w8a8_structured_scan_20260615.txt`
- `evidence/week2_hardening/w8a8_checkpoint_availability_check_20260615.txt`
- `evidence/week2_hardening/gsm8k_w8a8_accuracy_gap_summary_20260615.txt`

## 7. 当前状态总结

已完成的 GPU 侧补充验证包括：

- 128K BF16 启动与 smoke validation；
- 512K BF16 启动与 500K near-limit 请求；
- 512K FP8 KV 启动与 500K near-limit 请求；
- FP8 KV Cache 容量与 512K 请求并发余量对比；
- 50 题轻量代码生成验证；
- GSM8K/W8A8 证据扫描；
- W8A8 checkpoint 可用性检查；
- GPU 服务停止快照。

仍需在文档中保持严格口径的内容包括：

- INT8/AWQ/GPTQ 等量化路径需要按失败日志说明边界；
- 显存收益应限定为模型加载显存下降；
- W8A8 GSM8K accuracy 未完成实测，应列为后续补测项；
- 代码生成 50 题结果只能作为轻量验证，不作为完整 benchmark 结论。
