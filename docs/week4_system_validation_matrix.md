# Week4 系统验证与交付追踪矩阵

## 1. 目的与使用范围

本文档用于统一追踪推理服务系统的能力实现、验证状态、原始证据、已知边界和待完成工作。

每项能力只有在以下内容完整时，才可标记为“已验证”：

1. 对应实现已存在；
2. 已执行可复现测试或实验；
3. 原始日志、指标、CSV、JSON 或截图已归档；
4. 结论的适用范围和限制已明确记录。

## 2. 状态定义

| 状态 | 含义 |
|---|---|
| 已验证 | 实现、测试和原始证据完整，适用边界明确。 |
| 待最终验证 | 已有实现或局部验证，仍需在目标运行环境完成最终实验。 |
| 待补充证据 | 实现与部分结果存在，但证据链、实验协议或归档不完整。 |
| 待实现 | 尚未形成满足目标能力定义的真实实现。 |
| 不适用 | 不属于当前系统运行范围，或不应作为本阶段结论。 |

---

## 3. 系统能力验证矩阵

### 3.1 Seed-OSS 服务接入、长上下文与推理预算

| 项目 | 内容 |
|---|---|
| 能力 | 基于 FastAPI 和 vLLM 提供 Seed-OSS-36B 推理 API，支持 `thinking_budget` 控制与长上下文边界验证。 |
| 主要实现 | `app/main.py`、`app/inference.py`、`app/backends/vllm_backend.py`。 |
| 当前状态 | 待最终验证 |
| 已有验证 | Seed-OSS vLLM serving、`thinking_budget` 传递、长上下文 near-limit / serving boundary 实验。 |
| 已有证据 | `docs/week2/seed_oss_128k_context_boundary_review.md`、`scripts/run_seed_oss_512k_near_limit_request_20260614.py`、相关 Week2 evidence。 |
| 已知边界 | 长上下文结论属于 serving boundary validation；不应表述为固定工作负载下的常态 SLA。 |
| 待完成工作 | 统一归档目标环境下的模型配置、KV Cache 约束、成功请求、失败边界和运行快照。 |

### 3.2 W8A8 量化、动态 batching 与 KV Cache 优化

| 项目 | 内容 |
|---|---|
| 能力 | 使用 W8A8 compressed-tensors artifact 进行 vLLM serving，并验证显存、吞吐、延迟、batching 与 KV Cache 行为。 |
| 主要实现 | `scripts/quantization/quantize_seed_oss_36b_w8a8.py`、vLLM serving scripts、Prometheus metrics 和 benchmark scripts。 |
| 当前状态 | 已验证，待最终汇总 |
| 已有验证 | FP32 与 W8A8 serving 对照；并发矩阵；KV Cache、Prefix Cache、长上下文边界和质量评测。 |
| 已有证据 | `docs/week2_quantization_feasibility_report.md`、`docs/week2_quantization_protocol_audit.md`、`docs/week2_performance_optimization_report.md`、`evidence/week2_hardening/`。 |
| 已知边界 | 当前稳定 serving 路线为 W8A8 compressed-tensors；不应泛化为所有 INT8、AWQ、GPTQ 或 runtime quantization 路线。 |
| 待完成工作 | 在最终目标部署拓扑下补充 workload 级吞吐、P50/P95、error rate 与 GPU 指标快照。 |

### 3.3 Redis Stream 异步任务调度与恢复

| 项目 | 内容 |
|---|---|
| 能力 | 支持异步任务提交、consumer group 消费、PEL 管理、worker crash 后 `XAUTOCLAIM` 接管。 |
| 主要实现 | `app/redis_stream_jobs.py`、`app/job_worker.py`、`app/job_runtime.py`、`POST /jobs`、`GET /jobs/{job_id}`。 |
| 当前状态 | 已验证，待最终目标环境联调 |
| 已有验证 | 正常异步任务处理；worker 业务异常；worker 进程故障后 PEL 遗留、replacement worker reclaim、任务完成与 PEL 清空。 |
| 已有证据 | `evidence/week4_redis/async_jobs_mock_e2e_worker_metrics_20260629.txt`；`evidence/week4_redis/async_jobs_worker_crash_reclaim_e2e_20260629.txt`。 |
| 已知边界 | 采用 at-least-once 处理语义；推理执行与状态提交之间存在重复执行边界。 |
| 待完成工作 | 在真实模型 upstream 下验证 submit latency、completion latency、队列堆积、worker 吞吐与故障接管。 |

### 3.4 高可用、共享熔断与降级策略

| 项目 | 内容 |
|---|---|
| 能力 | Gateway 多副本、Nginx 负载均衡、Kubernetes HPA、retry、circuit breaker、fallback 和低预算降级。 |
| 主要实现 | `deployment/week3_ha/`、`app/resilience.py`、`app/redis_circuit_breaker.py`、`app/inference.py`。 |
| 当前状态 | 已验证，待真实双 upstream 最终验证 |
| 已有验证 | Gateway 多副本、anti-affinity、probes、rolling update、Pod recovery、Gateway HPA、primary/fallback 切换、breaker recovery。 |
| 已有证据 | `evidence/week3_ha/`、`docs/week3_delivery_report.md`。 |
| 已知边界 | HPA 已验证 Gateway CPU 层扩缩容；未验证 GPU/vLLM instance autoscaling。 |
| 待完成工作 | 在双 TP=2 真实 upstream 环境下完成 primary failure、fallback、shared breaker open、recovery probe 和 primary recovery 的最终闭环。 |

### 3.5 压力测试与容量分层

| 项目 | 内容 |
|---|---|
| 能力 | 对接入层和模型执行层分别进行吞吐、P50/P95、错误率和稳定性测试。 |
| 主要实现 | `loadtest/`、`scripts/week4_cloud/benchmark_gateway_capacity.py`。 |
| 当前状态 | 待最终验证 |
| 已有验证 | JMeter `/jobs` 固定 QPS 计划、稳定窗口校验、evidence wrapper 与 wrk admission smoke 已在本地 Mock 环境验证。 |
| 已有证据 | 本地 smoke 输出；`scripts/week4_cloud/benchmark_gateway_capacity.py`。 |
| 已知边界 | `/jobs` admission 吞吐与模型端到端完成吞吐必须分开统计与解释。 |
| 待完成工作 | 在目标 GPU 环境完成 `/jobs` admission 的 100 / 500 / 1000 QPS 正式压测；归档 JTL、HTML report、Gateway metrics、Redis queue / PEL 状态和运行时快照。 |

### 3.6 资源压力、OOM 与节点故障

| 项目 | 内容 |
|---|---|
| 能力 | 在节点或 upstream 故障、资源压力和请求超限条件下验证拒绝、降级、恢复和可观测性。 |
| 主要实现 | Gateway resilience controller、Redis shared breaker、fallback upstream、Redis Stream worker reclaim。 |
| 当前状态 | 待最终验证 |
| 已有验证 | Gateway / Pod / primary upstream 故障、fallback、breaker 和 worker crash reclaim。 |
| 已有证据 | `evidence/week3_ha/real_failover/`；`evidence/week4_redis/`。 |
| 已知边界 | 尚未形成真实 GPU memory pressure 或 KV Cache exhaustion 的最终实验闭环。 |
| 待完成工作 | 固化并执行 primary vLLM kill/restart、资源压力、请求超限、恢复后的指标和状态验证。 |

### 3.7 BAGEL 图文联合推理

| 项目 | 内容 |
|---|---|
| 能力 | 提供图文联合推理能力，并评估不同图像尺寸、prompt 长度和并发条件下的稳定性与资源消耗。 |
| 主要实现 | `scripts/week3_bagel/`、BAGEL runtime / gateway 相关部署资产。 |
| 当前状态 | 待最终验证 |
| 已有验证 | 历史 BAGEL understanding benchmark 与基础联通性验证。 |
| 已有证据 | `scripts/week3_bagel/run_understanding_benchmark.py`、历史 Week3 BAGEL evidence。 |
| 已知边界 | 已固定三个图文场景，每场景重复 10 次；该设计用于稳定性统计，不代表 30 个独立图像场景。 |
| 待完成工作 | 完成图像尺寸、prompt 长度、并发度矩阵；归档成功率、P50/P95、失败样本与资源指标。 |

### 3.8 业务 workload 与模型对照

| 项目 | 内容 |
|---|---|
| 能力 | 针对客服、长文本和代码生成 workload 进行真实端到端验证，并在固定协议下完成模型对照。 |
| 主要实现 | `data/eval/codegen_mini.jsonl`、`scripts/run_seed_oss_codegen_eval_20_20260614.py`、相关评测脚本。 |
| 当前状态 | 待实现 |
| 已有验证 | Seed 代码生成历史评测和部分 reasoning / code generation 结果。 |
| 已有证据 | `data/eval/codegen_mini.jsonl`、`scripts/eval_week2_reasoning_codegen.py`、Week2 代码生成 evidence。 |
| 已知边界 | 不同模型、prompt template、dtype、kernel 或服务参数不同的结果不能直接视为绝对质量排名。 |
| 待完成工作 | 固定客服、长文本、代码生成 workload；固定模型版本、参数、硬件与并发协议；完成 Seed 与 Qwen 对照并分开报告质量与性能。 |

### 3.9 Triton RMSNorm-INT8 融合算子

| 项目 | 内容 |
|---|---|
| 能力 | 实现 BF16/FP16 activation 的 RMSNorm 与 per-row INT8 quantization 融合算子。 |
| 主要实现 | `app/kernels/rmsnorm_int8.py`、`tests/test_rmsnorm_int8.py`、`scripts/week4_cloud/benchmark_triton_rmsnorm_int8.py`。 |
| 当前状态 | 待 GPU 最终验证 |
| 当前事实 | 已实现 PyTorch reference、Triton kernel、CPU correctness tests 与 A100 benchmark 入口；CUDA/Triton correctness、性能和 profiling 尚未执行。 |
| 必须完成 | PyTorch unfused reference；Triton fused kernel；多 shape、多 dtype 正确性测试；A100 latency / speedup / throughput benchmark；环境快照和原始 CSV。 |
| 最终边界 | 在未完成 vLLM custom-op 集成前，该模块定位为独立 inference microkernel，不表述为已替换 vLLM 主 serving 路径。 |
| 待完成工作 | 在 CUDA/Triton GPU 环境完成多 shape、多 dtype correctness、A100 latency/speedup/throughput、profiling 与原始 CSV/环境快照归档。 |

### 3.10 部署、运维与交付材料

| 项目 | 内容 |
|---|---|
| 能力 | 提供可复现部署脚本、运行说明、故障处理、实验复现与交付材料。 |
| 主要实现 | `deployment/`、`docs/`、`evidence/`、Week4 cloud scripts。 |
| 当前状态 | 待最终收口 |
| 已有验证 | Week2 / Week3 部署文档、架构图、SOP、监控资产、cloud launch scripts。 |
| 已有证据 | `docs/repo_structure_guide.md`、`docs/week3_delivery_report.md`、`deployment/`。 |
| 待完成工作 | Dockerfile / compose 或等价部署方案；Week4 压测报告；运行与故障处理指南；系统演示脚本与最终技术总结材料。 |

---

## 4. GPU 实验前准备清单

以下项目完成、验证并提交后，方可进行目标 GPU 环境实验：

- [ ] 安装并验证 JMeter 和 wrk
- [ ] 完成 `/jobs` admission 的 100 / 500 / 1000 QPS 参数化压测计划
- [ ] 完成 `/generate` 执行层压测计划
- [ ] 完成 Gateway、Redis、runtime metrics 自动采集脚本
- [ ] 固定客服、长文本和代码生成 workload
- [ ] 固定 BAGEL 多模态样本 manifest
- [ ] 固定模型对照协议
- [ ] 完成 primary failure、worker failure、resource pressure 实验脚本
- [ ] 完成 Triton reference、测试骨架和 benchmark 数据格式
- [ ] 完成部署与运维文档骨架
- [ ] 确认 Git 工作区干净

---

## 5. 目标 GPU 环境实验顺序

1. 双 TP=2 Seed W8A8 upstream 启动与 readiness 验证；
2. Gateway、Redis shared breaker 与 async worker 联通；
3. primary / fallback、breaker open 与 recovery 验证；
4. `/jobs` admission 100 / 500 / 1000 QPS 压测；
5. `/generate` 执行层并发矩阵；
6. 长文本、代码生成与动态预算 workload；
7. 资源压力、OOM 边界和节点故障恢复；
8. BAGEL 多模态场景矩阵；
9. Seed 与 Qwen 受控对照；
10. Triton RMSNorm-INT8 融合算子正确性、性能和 profiling；
11. 实验结果归档、报告收口与部署文档更新。

