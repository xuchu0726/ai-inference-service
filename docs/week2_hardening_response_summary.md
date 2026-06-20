# Week2 Hardening 补充验证总结

## 1. 文档目的

本文档汇总 Week2 性能优化实验后的补充验证工作，重点记录长上下文推理、FP8 KV Cache、W8A8 量化路径、代码生成验证、显存统计口径、GSM8K 精度回归和环境复现边界的最终结果。

本文档仅基于仓库中已提交的 evidence、results、logs、scripts 和 docs 进行总结，不对未实测内容作推断。所有结论均限定在当前模型、硬件、serving engine、评测脚本和实验参数范围内。

## 2. 补充验证范围

本轮补充验证围绕以下工程问题展开：

- 将 512K 长上下文从可行性分析推进到 4×A100 环境下的真机启动与 near-limit 请求验证；
- 验证 FP8 KV Cache 对长上下文 KV Cache 容量和 serving headroom 的影响；
- 完成 W8A8 compressed-tensors checkpoint 的持久化检查、vLLM serving、smoke test 和 GSM8K full benchmark；
- 明确 W8A8 显存收益的统计口径，区分模型加载显存与运行时总显存；
- 将代码生成验证扩展到 50 个轻量函数生成任务，并记录失败类型和验证边界；
- 归档环境构建、安装失败、I/O error 和 Git 提交流程中的复现证据。

## 3. 512K 长上下文与 FP8 KV Cache 验证

### 3.1 BF16 KV 512K 配置验证

补充实验在 4×A100-SXM4-80GB 环境下，对 Seed-OSS-36B-Instruct 的 512K 长上下文 serving 配置进行了真机验证。

实验配置如下：

- 模型：`ByteDance-Seed/Seed-OSS-36B-Instruct`
- Serving engine：vLLM
- Tensor parallel size：4
- `max_model_len`：524288
- Model dtype：bfloat16
- API：OpenAI-compatible `/v1/chat/completions`

实测结果如下：

- vLLM 成功接受 `max_model_len=524288` 配置；
- 服务完成启动并进入 `Application startup complete` 状态；
- 约 500K prompt tokens 的 near-limit 请求成功返回；
- 实际 `prompt_tokens` 为 500,033；
- `total_tokens` 为 500,065；
- HTTP status 为 200；
- 端到端 latency 为 533.85s；
- 实验过程中未观察到 OOM、进程退出或 RuntimeError。

该结果将原先的 512K 可行性分析补充为 4×A100 环境下的真机边界验证。但该实验仍属于单请求 near-limit 验证，不等同于覆盖所有生产并发场景或不同 workload 下的 512K serving 性能。

相关证据：

- `evidence/week2_hardening/seed_oss_4xa100_512k_ready_evidence_20260614.txt`
- `results/week2_hardening/seed_oss_4xa100_512k_near_limit_summary_20260614.json`
- `results/week2_hardening/seed_oss_4xa100_512k_near_limit_response_20260614.json`
- `evidence/week2_hardening/seed_oss_4xa100_512k_near_limit_result_evidence_20260614.txt`
- `logs/week2_hardening/seed_oss_4xa100_512k_near_limit_request_20260614.log`

### 3.2 FP8 KV 512K 配置验证

在相同 4×A100 环境下，进一步验证了 `kv_cache_dtype=fp8` 的 512K serving 配置。

主要配置差异为：

- `kv_cache_dtype=fp8`

实测结果如下：

- vLLM 成功接受 `max_model_len=524288` 与 `kv_cache_dtype=fp8` 配置；
- 服务完成启动并进入 `Application startup complete` 状态；
- vLLM 日志确认使用 FP8 数据类型存储 KV Cache；
- GPU KV cache size 从 BF16 KV 配置下的 909,360 tokens 提升到 1,807,008 tokens；
- 524,288-token request 的 theoretical concurrency 从 1.73x 提升到 3.45x；
- 约 500K prompt tokens 的 FP8 KV near-limit 请求成功返回；
- 实际 `prompt_tokens` 为 500,037；
- `total_tokens` 为 500,069；
- HTTP status 为 200；
- 端到端 latency 为 770.60s。

按 vLLM 日志计算，FP8 KV Cache 将 KV Cache 容量和 512K 请求的 theoretical concurrency 约提升 1.99 倍。该结果说明 FP8 KV 对长上下文 serving 的容量边界和并发余量有明显帮助。

同时，单个 500K near-limit 请求中，FP8 KV 的端到端 latency 高于 BF16 KV。因此，本实验结论应限定为 KV Cache 容量和 serving headroom 提升，不应解释为单请求 latency 优化。

相关证据：

- `evidence/week2_hardening/seed_oss_4xa100_512k_fp8kv_ready_evidence_20260614.txt`
- `results/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_summary_20260614.json`
- `results/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_response_20260614.json`
- `evidence/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_result_evidence_20260614.txt`
- `evidence/week2_hardening/seed_oss_4xa100_512k_bf16_vs_fp8kv_summary_20260614.txt`
- `logs/week2_hardening/seed_oss_4xa100_512k_fp8kv_near_limit_request_20260614.log`

## 4. W8A8 量化路径与 serving 验证

### 4.1 W8A8 compressed-tensors 路径

当前项目已完成 Seed-OSS-36B-Instruct 的 W8A8 compressed-tensors 离线量化、checkpoint 持久化检查、vLLM serving、smoke test、并发压测和 GSM8K full benchmark。

最新 checkpoint 检查结果如下：

- W8A8 checkpoint 路径：`/workspace/models/Seed-OSS-36B-Instruct-W8A8`
- checkpoint 大小：约 36G
- safetensors 分片数：8
- `config.json` 中包含 compressed-tensors 量化配置；
- `quant_method`：`compressed-tensors`
- `quantization_status`：`compressed`

模型权重文件未提交到 Git 仓库。仓库只保存 checkpoint 持久化检查记录、serving 日志、benchmark 结果和复现实验脚本。

已完成内容包括：

- 离线生成 W8A8 compressed-tensors checkpoint；
- 在 clean volume 环境中确认 W8A8 checkpoint 持久化存在；
- 使用 vLLM compressed-tensors 后端加载 W8A8 模型；
- 日志确认使用 `CompressedTensorsW8A8Int8 / CutlassScaledMMLinearKernel` 路径；
- 完成 W8A8 serving smoke test；
- 完成 deterministic smoke test；
- 完成 W8A8 full GSM8K benchmark；
- 生成 BF16 baseline 与 W8A8 accuracy 对比结果；
- 归档环境、脚本、日志、结果和 checkpoint 检查证据。

相关证据：

- `evidence/week2_hardening/w8a8_clean_volume_quantization_success_summary_20260615.txt`
- `evidence/week2_hardening/w8a8_clean_volume_quantization_final_status_20260615.txt`
- `logs/week2_hardening/w8a8_clean_volume_offline_quantization_20260615.log`
- `evidence/week2_hardening/w8a8_checkpoint_persistence_check_20260616.txt`
- `evidence/week2_hardening/w8a8_serving_env_snapshot_20260616.txt`
- `evidence/week2_hardening/w8a8_vllm_ready_smoke_20260616.txt`
- `evidence/week2_hardening/w8a8_vllm_delayed_ready_check_20260616.txt`
- `evidence/week2_hardening/w8a8_vllm_authenticated_smoke_20260616.txt`
- `evidence/week2_hardening/w8a8_vllm_deterministic_smoke_20260616.txt`
- `evidence/week2_hardening/w8a8_generate_adapter_smoke_20260616.txt`
- `logs/week2_hardening/w8a8_generate_adapter_20260616.log`
- `scripts/week2_hardening/vllm_generate_adapter.py`

### 4.2 历史 serving 与性能对比证据

早期实验已完成 W8A8 serving、smoke test、batch profile 并发压测和 FP32/W8A8 batch profile 对比。该部分结果仍作为 W8A8 serving 性能和显存收益分析的历史证据，但需要与最新 clean volume checkpoint、serving 和 GSM8K 精度回归结果合并解释。

历史证据主要说明：

- W8A8 compressed-tensors 是当前项目已经跑通的稳定量化路径；
- W8A8 能降低模型加载阶段的显存占用；
- W8A8 的 serving 性能和并发 profile 已有独立测试记录；
- 最新 GSM8K 精度回归补齐了此前缺少的 accuracy 对比。

相关证据：

- `docs/week2_quantization_feasibility_report.md`
- `docs/week2_quantization_strategy.md`
- `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`
- `logs/new_2xa100_seed_oss_w8a8_offline_quantization_success_inventory_20260528.txt`
- `logs/new_2xa100_seed_oss_w8a8_ready_evidence_20260528.txt`
- `logs/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_summary_20260528.txt`

### 4.3 其他量化路径边界

对原始 BF16 checkpoint 直接使用 compressed-tensors / strict INT8 类 serving 的尝试未能形成稳定结果。日志显示，该路径需要预量化 checkpoint 中包含 compressed-tensors 后端所需的量化配置字段。

主要缺失字段包括：

- `target_scheme_map`
- `quant_format`
- `sparsity_scheme_map`
- 其他 compressed-tensors 配置字段

该结果说明，原始 BF16 checkpoint 不能仅依靠运行时参数直接变成严格 INT8/W8A8 compressed-tensors serving；该路径需要预量化产物或完整离线量化流程。

INT8、AWQ、GPTQ 等其他量化路径当前只作为兼容性边界和失败日志记录，未形成稳定 serving 结果。

相关证据：

- `logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt`
- `logs/new_2xa100_seed_oss_compressed_tensors_int8_vllm_launch_20260528.log`
- `logs/new_2xa100_seed_oss_quantization_process_appendix_20260528.txt`
- `evidence/week2_hardening/w8a8_vllm_install_io_error_diagnosis_20260615.txt`
- `evidence/week2_hardening/w8a8_vllm_serving_venv_io_error_20260615.txt`
- `evidence/week2_hardening/w8a8_workspace_venv_install_unstable_conclusion_20260615.txt`

## 5. GSM8K baseline 与 W8A8 精度回归

### 5.1 BF16/vLLM baseline

仓库中已有完整 GSM8K baseline 结果：

- 文件：`results/week2_gsm8k_full_seed_oss_budget0_summary.csv`
- 总题数：1319
- 正确题数：999
- accuracy：75.7392%
- backend：vLLM
- `max_new_tokens`：256

该结果解释为 Seed-OSS-36B-Instruct 在 BF16/vLLM serving 路径下的数学推理 baseline。

### 5.2 W8A8 GSM8K full benchmark

本次补充完成了 W8A8 compressed-tensors serving profile 下的 GSM8K full benchmark，使用相同 GSM8K test split、相同评测脚本、相同生成参数和相同 vLLM serving 口径。

W8A8 结果如下：

- 文件：`results/week2_hardening/gsm8k_w8a8_full_budget0_fixed_summary_20260616.csv`
- 总题数：1319
- API 成功题数：1319
- API 失败题数：0
- API error rate：0.0%
- 可解析答案题数：1319
- 正确题数：986
- accuracy：74.7536%
- 平均 tokens/s：23.8375
- 平均输出 tokens：206.2790

与 BF16/vLLM baseline 对比：

| Profile | Total | Correct | Accuracy |
|---|---:|---:|---:|
| BF16/vLLM baseline | 1319 | 999 | 75.7392% |
| W8A8 compressed-tensors | 1319 | 986 | 74.7536% |

精度差异如下：

- 绝对下降：0.9856 percentage points；
- 正确题数减少：13；
- API error rate：0.0%。

W8A8 compressed-tensors profile 在完整 GSM8K test split 上的原始 accuracy 为 74.7536%，相比 BF16/vLLM baseline 的 75.7392% 低 0.9856 个百分点。该差异保留为固定 `max_new_tokens=256` 条件下的历史观察结果，同时两条路线均保持 API error rate 为 0。

后续输出上限审计发现，BF16 与 W8A8 的大量错误集中在 `output_tokens == 256` 的触顶样本中。因此，上述 0.9856 percentage points 不再作为最终 quantization quality regression 结论，而应解释为短输出预算下的原始 serving behavior。统一的协议边界、cap-hit 审计和后续定向复测规则见 `docs/week3_quantization_protocol_audit.md`。

该结果仅适用于本次 Seed-OSS-36B-Instruct、vLLM、compressed-tensors W8A8 checkpoint、GSM8K test split 和当前生成参数组合，不应泛化为所有任务、所有模型或所有量化格式上的固定精度损耗。

相关证据：

- `results/week2_gsm8k_full_seed_oss_budget0_summary.csv`
- `results/week2_hardening/gsm8k_w8a8_full_budget0_fixed_summary_20260616.csv`
- `results/week2_hardening/gsm8k_w8a8_full_budget0_fixed_20260616.csv`
- `evidence/week2_hardening/gsm8k_w8a8_full_budget0_fixed_check_20260616.txt`
- `logs/week2_hardening/gsm8k_w8a8_full_budget0_fixed_20260616.log`
- `scripts/week2_hardening/vllm_generate_adapter.py`
- `data/eval/gsm8k_test.jsonl`

### 5.3 评测修正过程

本次 W8A8 GSM8K full benchmark 前进行了多轮诊断，以排除 adapter、thinking budget、输出解析和请求稳定性问题。

主要修正包括：

- 检查 GSM8K 数据文件、baseline summary 和评测脚本；
- 检查历史 BF16/vLLM baseline 口径；
- 增加 W8A8 vLLM generate adapter；
- 修正 `thinking_budget` 控制方式；
- 进行 3 题、10 题和多种输出长度配置的诊断运行；
- 确认 full run 结果中 API 成功率为 100%。

相关证据：

- `evidence/week2_hardening/gsm8k_file_inventory_20260616.txt`
- `evidence/week2_hardening/gsm8k_script_inspection_20260616.txt`
- `evidence/week2_hardening/gsm8k_script_key_lines_20260616.txt`
- `evidence/week2_hardening/gsm8k_historical_result_summary_20260616.txt`
- `evidence/week2_hardening/gsm8k_w8a8_file_index_20260615.txt`
- `evidence/week2_hardening/gsm8k_w8a8_structured_scan_20260615.txt`
- `evidence/week2_hardening/gsm8k_w8a8_accuracy_gap_summary_20260615.txt`
- `evidence/week2_hardening/w8a8_checkpoint_availability_check_20260615.txt`
- `evidence/week2_hardening/gsm8k_w8a8_diagnostic_10_budget0_fixed_check_20260616.txt`
- `evidence/week2_hardening/gsm8k_w8a8_full_stall_check_20260616_112027.txt`
- `results/week2_hardening/gsm8k_w8a8_diagnostic_10_budget0_fixed_summary_20260616.csv`
- `logs/week2_hardening/gsm8k_w8a8_diagnostic_10_budget0_fixed_20260616.log`

## 6. 代码生成验证补充

原有代码生成验证样本数量较少，因此补充了 50 个 HumanEval/MBPP-style 的轻量函数生成任务，并为每个任务设置本地 Python 单元测试。

实验配置如下：

- 模型：`ByteDance-Seed/Seed-OSS-36B-Instruct`
- Serving profile：512K FP8 KV
- GPU：4×A100-SXM4-80GB
- Tensor parallel size：4
- API：OpenAI-compatible `/v1/chat/completions`
- 验证方式：本地 Python 单元测试

该评测不是官方 HumanEval 或 MBPP 完整 benchmark，而是轻量函数生成验证。

初版 20 题中，API 请求均返回 HTTP 200，但本地单元测试全部失败。检查结果显示，主要问题不是服务不可用，而是初版 prompt、generation budget 和代码提取逻辑对 Seed-OSS 输出格式控制不足，模型输出容易被 thinking tag 或非最终代码内容占用。

随后进行了修正版评测，调整包括：

- 增加 `max_tokens`；
- 使用更严格的 code-only system prompt；
- 增强代码块和函数定义提取逻辑；
- 保留每题原始输出、提取代码、错误信息和测试结果。

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

该结果说明服务能够稳定响应代码生成请求，并在部分轻量函数生成任务中生成可执行且通过单元测试的代码。但通过率不高，因此该实验只能作为 serving、输出解析和基础代码生成链路验证，不能作为完整代码生成 benchmark 结论。

相关证据：

- `results/week2_hardening/seed_oss_codegen_eval_20_repair_summary_20260614.json`
- `results/week2_hardening/seed_oss_codegen_eval_additional_30_summary_20260615.json`
- `results/week2_hardening/seed_oss_codegen_eval_20_repair_detail_20260614.json`
- `results/week2_hardening/seed_oss_codegen_eval_additional_30_detail_20260615.json`
- `evidence/week2_hardening/seed_oss_codegen_eval_50_summary_20260615.txt`
- `logs/week2_hardening/seed_oss_codegen_eval_20_repair_20260614.log`
- `logs/week2_hardening/seed_oss_codegen_eval_additional_30_20260615.log`

## 7. 显存收益统计口径

W8A8 量化实验中的显存收益需要区分“模型加载显存”和“运行时总显存”。

当前统计结果如下：

- W8A8 明显降低模型权重加载阶段的显存占用；
- 模型加载显存从 67.59 GiB 降至 17.71 GiB；
- 对应降幅为 73.8%；
- 运行时 `nvidia-smi` 总显存没有按相同比例下降，因为 vLLM 会将释放出的显存预算用于扩展 KV Cache、batching 和 serving buffer。

模型加载显存下降说明 W8A8 降低了权重加载阶段的 GPU memory footprint。运行时总显存不应按 `nvidia-smi` 占用量简单比较，因为 serving engine 会根据显存预算分配 KV Cache 和运行时缓冲区。对 serving 系统而言，更合理的收益解释是：W8A8 降低权重占用后释放了更多 serving headroom，可用于更长上下文、更高 batch/token capacity 或更稳的并发配置。

相关证据：

- `logs/new_2xa100_seed_oss_fp32_vs_w8a8_quantization_summary_20260528.txt`
- `docs/week2_quantization_feasibility_report.md`
- `results/new_2xa100_seed_oss_fp32_vs_w8a8_batchprofile_improvement_20260529.csv`
- `evidence/week2_hardening/w8a8_checkpoint_persistence_check_20260616.txt`
- `evidence/week2_hardening/w8a8_serving_env_snapshot_20260616.txt`

## 8. 环境复现与故障归档

本轮补充实验中，环境构建过程暴露出多类工程问题，已按复盘价值归档。

已记录的问题包括：

- `/workspace` 或 venv 环境中的 I/O error；
- vLLM 安装过程中的依赖安装失败；
- clean volume 环境下的 toolchain 检查；
- BF16 checkpoint 下载与完整性检查；
- W8A8 离线量化过程记录；
- W8A8 checkpoint 持久化检查；
- GPU 服务停止前的关键结果持久化检查；
- Pod 切换后的 Git 工作区状态、远程同步状态和大文件提交风险检查；
- 推送 GitHub 前的目录结构审计和大文件风险检查。

环境故障日志不作为性能结论依据，但具有复盘价值，主要用于说明：

- 为什么需要 clean volume 重建；
- 为什么不能依赖临时 Pod 本地状态；
- 为什么 checkpoint、logs、results 和 evidence 需要及时归档；
- 为什么模型权重不应提交到 Git 仓库；
- 为什么需要区分 Network Volume 持久化数据和 GitHub 可复现实验资产。

相关证据：

- `evidence/week2_hardening/week2_hardening_repository_structure_audit_20260616.txt`
- `evidence/week2_hardening/pre_gpu_release_persistence_check_20260616.txt`
- `evidence/week2_hardening/seed_oss_36b_clean_download_launch_20260615.txt`
- `evidence/week2_hardening/seed_oss_36b_clean_download_progress_20260615.txt`
- `evidence/week2_hardening/seed_oss_36b_clean_download_complete_check_20260615.txt`
- `evidence/week2_hardening/tmp_io_health_check_20260615.txt`
- `evidence/week2_hardening/workspace_io_health_check_20260615.txt`
- `evidence/week2_hardening/w8a8_clean_volume_vllm_install_result_20260615.txt`
- `evidence/week2_hardening/w8a8_clean_volume_vllm_toolchain_check_20260615.txt`
- `evidence/week2_hardening/w8a8_vllm_install_io_error_diagnosis_20260615.txt`
- `evidence/week2_hardening/w8a8_vllm_serving_venv_io_error_20260615.txt`
- `evidence/week2_hardening/w8a8_workspace_venv_install_unstable_conclusion_20260615.txt`

## 9. 当前状态总结

本次补充验证已完成以下实验与证据归档：

- 128K BF16 启动与 smoke validation；
- 512K BF16 启动与 500K near-limit 请求；
- 512K FP8 KV 启动与 500K near-limit 请求；
- FP8 KV Cache 容量与 512K 请求并发余量对比；
- W8A8 compressed-tensors checkpoint 持久化检查；
- W8A8 vLLM serving smoke test；
- W8A8 deterministic smoke test；
- W8A8 GSM8K full benchmark；
- BF16 baseline 与 W8A8 accuracy 对比；
- 50 题轻量代码生成验证；
- W8A8 环境重建和安装故障归档；
- GitHub 证据提交与工作区清理。

基于当前证据，本文档的结论范围如下：

- 512K 长上下文 serving 已完成 4×A100 环境下的启动验证和 near-limit 请求验证；
- FP8 KV Cache 已验证可显著提升 KV Cache 容量和 512K 请求并发余量，但不能解释为单请求 latency 优化；
- W8A8 compressed-tensors 路径已完成离线量化、checkpoint 检查、serving、smoke test、并发压测和 GSM8K full benchmark；
- INT8/AWQ/GPTQ 等其他量化路径未形成稳定 serving 结果，当前只作为兼容性边界和失败日志记录；
- W8A8 显存收益对应模型加载显存下降，不代表运行时总 GPU 显存等比例下降；
- W8A8 GSM8K accuracy 已完成补测，较 BF16/vLLM baseline 下降约 0.99 个百分点；
- 50 题代码生成结果是轻量验证结果，不等同于官方 HumanEval 或 MBPP 完整 benchmark。
