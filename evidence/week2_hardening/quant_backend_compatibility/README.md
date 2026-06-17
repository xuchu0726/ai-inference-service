# Quant Backend Compatibility Evidence

本目录用于归档 Seed-OSS-36B 多量化后端兼容性补充验证证据。

当前新增范围仅覆盖 direct AWQ / direct GPTQ 在官方 BF16 checkpoint 上的最小启动边界验证。

已有 INT8 类路径不搬迁，继续保留在根目录历史日志中：

- logs/new_2xa100_seed_oss_bnb_int8_final_evidence_20260528.txt
- logs/new_2xa100_seed_oss_bnb_int8_retry_vllm_launch_20260528.log
- results/new_2xa100_seed_oss_bnb_int8_smoke_test_20260528.txt
- results/new_2xa100_seed_oss_bnb_int8_openai_benchmark_3req_20260528.csv
- logs/new_2xa100_seed_oss_compressed_tensors_int8_failure_summary_20260528.txt
- logs/new_2xa100_seed_oss_compressed_tensors_int8_vllm_launch_20260528.log
- logs/new_2xa100_seed_oss_inc_int8_failure_summary_20260528.txt
- logs/new_2xa100_seed_oss_inc_int8_vllm_launch_20260528.log
- logs/new_2xa100_seed_oss_strict_int8_root_cause_probe_20260528.txt

新增 AWQ/GPTQ 实验完成后，应保存：

- launch command
- checkpoint source
- vLLM / torch / CUDA / GPU versions
- full stdout / stderr
- whether EngineCore / Worker was reached
- whether `/v1/models` succeeded
- whether `/v1/chat/completions` succeeded
- failure root cause classification
