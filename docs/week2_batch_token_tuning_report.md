# Batch-Token 调优专项报告：Seed-OSS-36B 推理服务的 Workload-Aware Batching 分析

## 1. 实验背景

在 Seed-OSS-36B-Instruct 在线推理服务中，端到端性能不仅取决于模型规模和 GPU 资源，也受到推理框架调度策略、请求并发形态、输出长度、KV Cache 占用和 batch formation 能力的影响。

当前服务已采用 FastAPI + VLLMBackend + vLLM Server 的三层结构完成服务化部署。为了进一步分析不同 workload 下的吞吐与尾延迟表现，本专项实验围绕 vLLM 启动参数 `max_num_batched_tokens` 展开，观察该参数在短输出并发请求和长输出 decode-heavy 请求下对 QPS、P50/P95 latency、tokens/s 和 error rate 的影响。

本实验的目标不是寻找一个对所有场景都最优的固定参数，而是判断不同请求形态是否需要不同的 serving profile，并为后续 workload-aware routing 和服务调度策略提供数据依据。

## 2. 实验环境

本实验基于已完成部署的 Seed-OSS-36B-Instruct 推理服务进行。整体链路为：客户端 benchmark 脚本调用 FastAPI /generate 接口，FastAPI 通过 VLLMBackend 转发到 vLLM OpenAI-compatible 服务，由 vLLM 在 2 张 A100 80GB GPU 上执行模型推理。

| 项目 | 配置 |
|---|---|
| 云平台 | RunPod |
| GPU | 2 × NVIDIA A100-SXM4-80GB |
| 模型 | ByteDance-Seed/Seed-OSS-36B-Instruct |
| 推理框架 | vLLM |
| API 服务 | FastAPI + VLLMBackend |
| 精度 | BF16 |
| Tensor Parallel Size | 2 |
| 推理入口 | FastAPI /generate |
| 后端接口 | vLLM OpenAI-compatible API |
| 主要调优参数 | max_num_batched_tokens |
| 主要指标 | QPS、P50 latency、P95 latency、tokens/s、error rate |

实验结果主要来自 benchmark CSV、vLLM 启动日志、FastAPI 日志、metrics snapshot、图表脚本和本地保存的 evidence 文件。实验过程中保留了原始 CSV、汇总 CSV、图表、日志和项目目录快照，用于后续复现和结果追溯。

## 3. 实验设计

本实验将 max_num_batched_tokens 视为 vLLM serving profile 的 batch-token budget，而不是训练语境中的固定 batch size。该参数会影响 vLLM 在调度阶段能够容纳的 token 数量，从而影响 batch formation、请求等待、吞吐和尾延迟。

实验覆盖三类 workload：

| Workload | 目的 |
|---|---|
| short_output_c4 | 对 4096、8192、16384、32768 四组配置做基础扫描，观察短输出中等并发下的总体趋势 |
| short_output_c8 | 模拟短输出 burst 场景，重点观察 8192 与 32768 的首波请求延迟和 P95 表现 |
| long_output_c4 | 模拟长输出 decode-heavy 场景，验证较大的 batch-token budget 是否仍然稳定 |

测试过的 max_num_batched_tokens 配置包括 4096、8192、16384 和 32768。其中，8192 和 32768 被进一步用于 short-output c8 与 long-output c4 的重点对比。

该设计用于验证一个核心问题：max_num_batched_tokens 是否存在全局最优值，还是应根据 workload 类型进行 profile-level 调优。

## 4. Short-output c4 基础扫描结果

short-output c4 场景用于观察不同 max_num_batched_tokens 配置在短输出、中等并发请求下的总体趋势。

| max_num_batched_tokens | QPS | P50 latency (s) | P95 latency (s) | Avg tokens/s | Error rate |
|---:|---:|---:|---:|---:|---:|
| 4096 | 1.063 | 3.363 | 7.344 | 36.034 | 0.0 |
| 8192 | 1.090 | 3.336 | 6.625 | 36.487 | 0.0 |
| 16384 | 1.082 | 3.331 | 6.971 | 36.442 | 0.0 |
| 32768 | 1.101 | 3.331 | 6.339 | 36.655 | 0.0 |

从基础扫描结果看，32768 profile 在该场景下取得最高 QPS 和最低 P95 latency。相比 4096，32768 将 P95 latency 从 7.344s 降至 6.339s，说明更大的 batch-token budget 在短输出并发场景下对尾延迟有一定改善。

但 8192、16384、32768 之间的收益并非线性扩大，说明 max_num_batched_tokens 不宜被简单理解为“越大越好”。该参数的实际效果需要结合 workload 类型、输出长度和并发形态判断。

相关图表：

- figures/week2/batch_tokens/week2_batch_tokens_short_c4_qps.png
- figures/week2/batch_tokens/week2_batch_tokens_short_c4_p95.png

## 5. Short-output c8 Burst 场景分析

short-output c8 场景用于观察短输出 burst 请求下，8192 与 32768 两种 profile 对首波请求和 P95 latency 的影响。

| max_num_batched_tokens | QPS | P50 latency (s) | P95 latency (s) | Avg tokens/s | Error rate |
|---:|---:|---:|---:|---:|---:|
| 8192 | 1.921 | 3.361 | 7.350 | 33.998 | 0.0 |
| 32768 | 2.371 | 3.363 | 3.415 | 38.059 | 0.0 |

在该场景下，32768 profile 相比 8192 的表现更稳定：

| 指标 | 8192 | 32768 | 变化 |
|---|---:|---:|---:|
| QPS | 1.921 | 2.371 | 提升约 23.4% |
| P95 latency | 7.350s | 3.415s | 降低约 53.5% |
| Avg tokens/s | 33.998 | 38.059 | 提升约 11.9% |
| Error rate | 0.0 | 0.0 | 无错误 |

request-level 图表显示，8192 profile 在第一波 8 个并发请求中出现明显长尾，第一波平均 latency 约 7.345s；32768 profile 的第一波平均 latency 约 3.406s，后续 wave 也保持稳定。

该结果说明，在短输出 burst 场景下，更大的 batch-token budget 能提供更充足的 batch formation 空间，使首波请求更容易被一起调度，从而改善 P95 latency 和 burst handling 能力。

需要注意的是，本实验没有逐请求同步采集 vLLM queue metrics，因此这里将该现象解释为 batch formation 能力差异，而不直接归因为单一 queue 指标。

相关图表：

- figures/week2/batch_tokens/week2_batch_tokens_short_c8_qps.png
- figures/week2/batch_tokens/week2_batch_tokens_short_c8_p95.png
- figures/week2/batch_tokens/week2_batch_tokens_short_c8_first_wave_latency.png
- figures/week2/batch_tokens/week2_batch_tokens_short_c8_wave_latency.png

## 6. Long-output c4 Decode-heavy 场景分析

long-output c4 场景用于验证较大的 batch-token budget 在长输出 decode-heavy workload 下是否仍然稳定。

| max_num_batched_tokens | QPS | P50 latency (s) | P95 latency (s) | Avg tokens/s | Error rate |
|---:|---:|---:|---:|---:|---:|
| 8192 | 0.302 | 13.224 | 13.258 | 38.714 | 0.0 |
| 32768 | 0.288 | 13.264 | 16.406 | 37.012 | 0.0 |

在该场景中，32768 没有延续 short-output burst 下的优势：

| 指标 | 8192 | 32768 | 变化 |
|---|---:|---:|---:|
| QPS | 0.302 | 0.288 | 下降约 4.8% |
| P95 latency | 13.258s | 16.406s | 32768 高约 23.7% |
| Avg tokens/s | 38.714 | 37.012 | 下降约 4.4% |
| Error rate | 0.0 | 0.0 | 无错误 |

长输出请求的 decode 阶段占比更高，单个请求会持续占用 decode slots 和 KV cache。此时更大的 batch-token budget 不一定带来更低尾延迟，反而可能增加资源竞争和 tail latency 风险。

因此，long-output 或 mixed workload 更适合使用相对保守的 8192 profile。

相关图表：

- figures/week2/batch_tokens/week2_batch_tokens_long_c4_qps.png
- figures/week2/batch_tokens/week2_batch_tokens_long_c4_p95.png
- figures/week2/batch_tokens/week2_batch_tokens_long_c4_latency_boxplot.png

## 7. Workload-Aware Serving Profile 决策

综合 short-output burst 和 long-output decode-heavy 两类结果，本实验得到如下 profile-level 决策：

| Workload type | 推荐 profile | 依据 |
|---|---:|---|
| short_output_burst | 32768 | QPS 提升约 23.4%，P95 latency 降低约 53.5%，首波请求长尾明显改善 |
| long_output_or_mixed | 8192 | 长输出场景下 P95 latency 更稳定，避免 32768 带来的尾延迟恶化 |

该结果表明，max_num_batched_tokens 不存在对所有 workload 都最优的单一取值。短输出 burst 场景更依赖 batch formation 空间，而长输出 decode-heavy 场景更容易受到 decode 持续占用、KV cache 和资源竞争影响。

因此，后续推理服务不应只维护一个固定 batch-token 配置，而应根据请求类型、输出长度、并发形态和运行时指标维护不同 serving profile。

相关图表：

- figures/week2/batch_tokens/week2_batch_tokens_workload_qps_summary.png
- figures/week2/batch_tokens/week2_batch_tokens_workload_p95_summary.png
- figures/week2/batch_tokens/week2_batch_tokens_profile_decision.png

## 8. Workload-Aware Routing Policy 抽象

在 batch-token tuning 实验完成后，本项目进一步将 workload-aware serving profile 结论沉淀为轻量 routing policy abstraction。

新增代码模块：

- [`app/routing.py`](../app/routing.py)
- [`tests/test_routing.py`](../tests/test_routing.py)

该模块根据 `prompt_chars`、`max_new_tokens` 和 `concurrency_hint` 对请求进行 workload classification，并返回推荐 serving profile：

| Workload | 推荐 profile | max_num_batched_tokens |
|---|---|---:|
| short_output_burst | short_output_burst_32768 | 32768 |
| long_output_or_mixed | long_output_or_mixed_8192 | 8192 |

单元测试已覆盖 short-output burst、long-output 和 long-context 三类请求，测试结果为 `3 passed in 0.02s`。

该实现不代表已经完成生产级 gateway routing，也没有启动多个 vLLM 实例。当前价值在于把实测 batch-token tuning 结论转化为可测试、可扩展的工程策略模块，为后续多 serving profile、网关路由和服务降级策略提供代码基础。

详细说明见：

- [`docs/week2_routing_policy_abstraction.md`](../docs/week2_routing_policy_abstraction.md)

## 9. 动态批处理的工程边界说明

本实验完成的是 profile 级别的 batch-token 调优和 workload-aware serving profile 分析，不等同于完整的运行时动态批处理调度器。

原因是 max_num_batched_tokens 属于 vLLM 启动时调度参数，不适合在单个运行中的 vLLM engine 内直接热修改。更合理的工程设计是维护多个 serving profile，并在网关层根据 workload 类型进行路由。

当前阶段形成的工程链路为：

- profiling：通过不同 batch-token 配置采集 QPS、P95 latency、tokens/s 和 error rate；
- workload classification：区分 short-output burst 与 long-output decode-heavy 请求；
- serving profile decision：为不同 workload 选择 32768 或 8192 profile；
- 网关路由设计基础：为后续多 profile routing 和服务降级策略提供数据依据。

因此，当前结论应表述为：已完成 workload-aware batching policy foundation，而不是已实现完整生产级运行时动态批处理调度。

## 10. 工程意义与后续扩展方向

该实验对应大模型推理服务中的多个核心工程能力。

| 工程能力 | 本实验对应内容 |
|---|---|
| 大模型在线推理服务 | Seed-OSS-36B-Instruct + FastAPI + VLLMBackend + vLLM Server |
| Continuous Batching 分析 | 通过 concurrency 和 batch-token 实验观察吞吐与尾延迟变化 |
| Tail latency 优化 | 使用 P95 latency 和 first-wave latency 分析 burst 场景 |
| Throughput-latency trade-off | 同时比较 QPS、P95 latency、tokens/s 和 error rate |
| Workload-aware serving | 区分 short-output burst 和 long-output decode-heavy workload |
| 可复现实验 | 保存 CSV、日志、图表、脚本和目录快照 |
| 工程边界判断 | 明确区分 profile-level tuning 与 runtime scheduler |

该实验的价值不在于单纯修改一个参数，而在于基于真实 Seed-OSS-36B serving 数据，识别不同 workload 下的调度差异，并形成可解释、可复现、可继续工程化的 serving profile 策略。

## 11. 局限性

本实验仍存在以下限制：

1. 实验基于单组 RunPod 2 × A100 80GB 环境，结果受硬件、vLLM 版本和 workload 构造影响；
2. 当前重点分析 max_num_batched_tokens，尚未系统 sweep max_num_seqs、GPU memory utilization、prefix cache settings 等参数；
3. 当前实现是 profile-level tuning，不是真正多 vLLM 实例加 runtime gateway routing；
4. first-wave latency 分析没有逐请求同步采集 vLLM queue metrics，因此不能直接归因为单一 queue 指标；
5. workload 来自项目内 benchmark 构造，不等同于真实线上流量；
6. 32768 在 short-output burst 场景表现更好，但不能推广为所有场景下的最优配置；
7. long-output 场景只比较了 8192 和 32768，后续仍可加入更多输出长度和并发组合进行验证。

## 12. 结论

本专项实验完成了 Seed-OSS-36B-Instruct 推理服务在 vLLM serving 下的 batch-token tuning 与 workload-aware batching 分析。

主要结论如下：

1. max_num_batched_tokens 会显著影响 vLLM serving 的 QPS 和 P95 latency；
2. short-output c8 burst 场景中，32768 profile 相比 8192 将 QPS 从 1.921 提升到 2.371，并将 P95 latency 从 7.350s 降低到 3.415s；
3. long-output c4 decode-heavy 场景中，8192 profile 更稳健，P95 latency 为 13.258s，而 32768 为 16.406s；
4. max_num_batched_tokens 不存在全局最优配置，应根据 workload 类型选择 serving profile；
5. 对于生产化推理服务，更合理的动态批处理实现方式是多 serving profile 加网关路由，而不是运行时热修改单个 vLLM engine；
6. 本实验为后续网关路由、服务降级、高可用架构和压测验证提供了数据基础。

## 13. Evidence 清单

| 类型 | 路径 |
|---|---|
| Workload summary CSV | results/week2_batch_tokens_workload_summary_20260525.csv |
| Short c8 wave summary CSV | results/week2_batch_tokens_short_c8_wave_latency_summary_20260526.csv |
| 4096 benchmark CSV | results/week2_batch_tokens_4096_benchmark_20260525.csv |
| 8192 benchmark CSV | results/week2_batch_tokens_8192_benchmark_20260525.csv |
| 16384 benchmark CSV | results/week2_batch_tokens_16384_benchmark_20260525.csv |
| 32768 benchmark CSV | results/week2_batch_tokens_32768_benchmark_20260525.csv |
| 8192 c8 benchmark CSV | results/week2_batch_tokens_8192_c8_benchmark_20260525.csv |
| 32768 c8 benchmark CSV | results/week2_batch_tokens_32768_c8_benchmark_20260525.csv |
| 8192 long-output CSV | results/week2_batch_tokens_8192_long_output_512_benchmark_20260525.csv |
| 32768 long-output CSV | results/week2_batch_tokens_32768_long_output_512_benchmark_20260525.csv |
| Batch-token plotting script | scripts/plot_week2_batch_token_tuning.py |
| Request-level plotting script | scripts/plot_week2_batch_token_request_level.py |
| Workload QPS summary figure | figures/week2/batch_tokens/week2_batch_tokens_workload_qps_summary.png |
| Workload P95 summary figure | figures/week2/batch_tokens/week2_batch_tokens_workload_p95_summary.png |
| Profile decision figure | figures/week2/batch_tokens/week2_batch_tokens_profile_decision.png |
| First-wave latency figure | figures/week2/batch_tokens/week2_batch_tokens_short_c8_first_wave_latency.png |
| Wave-level latency figure | figures/week2/batch_tokens/week2_batch_tokens_short_c8_wave_latency.png |
| Figure reorg snapshot | logs/week2_batch_tokens_figure_reorg_snapshot_20260526.txt |
| Profile decision fix snapshot | logs/week2_batch_tokens_profile_decision_fix_snapshot_20260526.txt |
| Project tree snapshot | logs/project_full_tree_snapshot_20260526.txt |
