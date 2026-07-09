# Week4 最终交付报告：压测验收、异常验证与业务落地准备

## 1. 交付背景

本报告记录 Week3 反馈之后继续完成的补强工作，以及 Week4 压测验收与最终交付状态。

上一次阶段交付主要覆盖 Gateway 高可用接入层、Nginx、HPA、process-local circuit breaker、Primary/Fallback fallback 逻辑和 BAGEL 单 Pod 图文服务。

Week3 反馈指出三个主要改进方向：

1. HPA 只验证 Gateway 接入层，未覆盖 GPU vLLM 实例自动扩缩容。
2. circuit breaker 状态保存在单个 Gateway 进程内，未跨副本共享。
3. BAGEL 测试样本量较小，不能作为生产 SLA。

Week4 的补充目标是把系统推进到更完整的工程验收状态，包括真实双 TP=2 upstream、Redis shared breaker、JMeter/wrk admission 压测、controlled OOM fault injection、长文本、代码生成、多模态 workload 验证、Triton microkernel 和最终文档整理。

本项目仍定位为工程验证级交付，不表述为已经上线到真实用户流量的生产系统。

## 2. 最终系统范围

| 模块 | 内容 |
|---|---|
| 文本推理服务 | FastAPI Gateway + vLLM + Seed-OSS-36B W8A8 |
| 主备 serving | primary vLLM + fallback vLLM，双 TP=2，上游故障后 fallback |
| 请求接入 | /generate 同步生成，/jobs 异步 admission 与 Redis Stream 入队 |
| 容错 | timeout、bounded retry、Redis shared circuit breaker、fallback、低预算降级 |
| 压测 | JMeter 100/500/1000 QPS admission，wrk admission saturation |
| 长文本 | 512K 历史 profile 与 Week4 40K 级真实 workload |
| 多模态 | BAGEL 图文联合推理 API 与多案例 E2E 验证 |
| 代码生成 | Seed-OSS code generation workload 与功能评测证据 |
| 可观测性 | Prometheus / Grafana、请求指标、GPU / queue / KV 相关证据 |
| Microkernel | Triton RMSNorm-INT8 A100 correctness 与 microbenchmark |

## 3. 对 Week3 反馈的回应

### 3.1 HPA 只覆盖 Gateway 层

Week3 的 HPA 验证确实只覆盖 Gateway 接入层，使用 CPU load generator 和 MockBackend 验证 Gateway Pod 扩缩容。Week4 没有把 GPU vLLM 实例自动扩缩容包装成已完成。

Week4 的补充重点改为真实模型 serving 拓扑下的主备高可用验证：在 RunPod 4×A100 环境中部署 primary/fallback 两个 Seed-OSS W8A8 vLLM upstream，每个 upstream 使用 TP=2。该验证覆盖真实模型服务的 readiness、主 upstream 受控终止、fallback、恢复和健康状态。

边界：本项目最终没有实现 GPU utilization-based vLLM autoscaling，也没有把 GPU serving 实例 HPA 作为已完成结论。

### 3.2 熔断状态未跨副本共享

Week3 的熔断器为 process-local circuit breaker。Week4 进一步引入 Redis shared breaker，用于跨 Gateway 进程共享上游异常状态，并通过 controlled resource-exhaustion / shared-breaker harness 进行验证。

证据：

evidence/week4_resource_exhaustion/20260702T224556Z_shared_breaker_v2/

### 3.3 BAGEL 样本量较小

Week3 BAGEL 官方案例和电商商品图样本量较小，因此 P50/P95 只作为描述性统计，不作为生产 SLA。Week4 保留该边界，不将 BAGEL 小样本结果包装成生产级多模态性能基准。

证据：

results/week3_bagel/bagel_multicase_audit_summary_20260623.json
scripts/week4_cloud/run_bagel_workload_manifest.py

## 4. Week4 压测验收

### 4.1 JMeter 100/500/1000 QPS admission 压测

Week4 使用 JMeter 对 /jobs admission 路径进行 100 / 500 / 1000 QPS 固定速率压测。该路径覆盖 Gateway 接收请求、参数校验、Redis Stream 入队和 HTTP 202 Accepted 返回。

1000 QPS 档位结果：

| 指标 | 结果 |
|---|---:|
| 实际吞吐 | 约 1015.89 RPS |
| P95 latency | 约 5 ms |
| error rate | 0% |

证据：

evidence/week4_cloud/20260703T001000Z_real_gateway_redis_admission_jmeter/

边界：该指标不是 Seed-OSS-36B 完整生成路径的 1000 QPS；模型生成吞吐和延迟需要单独解释。

### 4.2 wrk admission saturation 压测

wrk 用于进一步观察 Gateway admission 路径的饱和能力。结果显示约 7627.65 RPS、P95 约 34.122 ms，connect/read/write/status errors 均为 0。

证据：

evidence/week4_cloud/20260703T002438Z_wrk_real_gateway_admission/

### 4.3 长文本、代码生成、多模态 E2E

| workload | 状态 | 证据 |
|---|---|---|
| 长文本 | 真实请求成功，最大输入约 38.9K tokens | evidence/week4_cloud/20260702_long_context_40960_profile/ |
| 代码生成 | 真实请求成功，保留响应和请求级 metrics | evidence/week4_cloud/20260702_codegen_fixed_e2e/ |
| 多模态 | BAGEL 图文联合推理多案例验证 | results/week3_bagel/bagel_multicase_audit_summary_20260623.json |

边界：这些 workload 是端到端执行验证，不表述为三类 workload 都完成 1000 QPS 模型生成压测。

### 4.4 Seed-OSS 超长上下文处理说明

Seed-OSS 的超长上下文能力分为两个验证层级记录。历史 4×A100 profile 已完成 500K+ token 近上限请求验证，用于证明模型和 serving stack 在高资源配置下具备超长上下文执行边界。Week4 的 TP=2 primary/fallback profile 主要用于主备切换、admission 压测、队列行为、容错和真实 workload 验证，不将 512K 写成该 profile 的常态 SLA。

工程上，长上下文处理不与 1000 QPS admission 指标混合解释。短任务 admission 用于验证高并发接入能力；长文本生成用于验证 prompt tokens、KV cache 占用、队列等待和长请求延迟边界。最终交付将两类指标分开记录，避免把接入层吞吐外推为完整模型生成吞吐。

### 4.5 BAGEL 多模态对齐能力说明

BAGEL 的验证范围是接口级图文联合理解能力。测试通过图像输入、文本 prompt 和模型响应之间的语义对应关系，观察模型是否能根据图像内容生成相关回答或商品文案草稿。该验证能够说明图像和文本在服务接口层形成了有效的多模态输入输出链路。

本项目没有复现或训练 BAGEL 内部的 vision-language alignment 机制，也不将小样本 P50/P95 统计写成生产级多模态 SLA。最终报告仅将其表述为图文联合推理 API 与多案例行为验证。


## 5. 异常场景验证

### 5.1 主 upstream 故障与恢复

在 RunPod 4×A100 环境中，系统部署 primary 和 fallback 两个 Seed-OSS W8A8 vLLM upstream。primary 受控终止后，Gateway 将请求切换到 fallback；primary 恢复后，服务健康状态恢复，后续请求可回到 primary。

证据：

evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/

### 5.2 Controlled CUDA-OOM fault injection

Week4 使用受控 CUDA-OOM fault injection 验证资源耗尽分类、Redis shared breaker、fallback 和恢复。该验证用于测试容错链路，不等同于真实 GPU 显存打满实验。

证据：

evidence/week4_resource_exhaustion/20260702T224556Z_shared_breaker_v2/

### 5.3 节点故障边界

项目中的节点宕机验证范围为主推理服务实例 / upstream 受控终止、fallback 与 recovery。没有验证整台 GPU 宿主机掉电、跨可用区故障或 Kubernetes worker node 真机宕机。

## 6. 性能优化与量化策略

W8A8 compressed-tensors serving 与 BF16 baseline 在固定协议下对比。模型加载显存从约 67.59 GiB 降至约 17.71 GiB，降低约 73.8%。同协议吞吐最低提升约 31.4%，支撑简历中的 29% 推理速度提升表述。

证据：

docs/week2_quantization_feasibility_report.md
results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv

边界：该结果不能泛化为所有 INT8、AWQ、GPTQ 或任意 workload。

## 7. Dynamic batching、KV Cache、FlashAttention 与 Triton

Week4 通过真实 TP=2 upstream 观察到 queue / dynamic batching / KV metrics。当前 4×A100 主备 TP=2 vLLM runtime 启动日志显示，vLLM backend selector 选择了 FLASH_ATTN backend。

证据：

evidence/week4_cloud/20260702T230508Z_real_primary_tp2_queue_kv_observation/
evidence/week4_cloud/20260703T004300Z_current_tp2_flashattn_runtime/

边界：FlashAttention 是 vLLM 自动选择并实际启用的 runtime backend，不是本项目手写或改造的 FlashAttention 算子。

Triton RMSNorm-INT8 融合算子完成 A100 correctness 与 microbenchmark。其结果属于独立 microkernel 级别，不表述为已替换 vLLM 主 serving 路径。

证据：

app/kernels/rmsnorm_int8.py
evidence/week4_cloud/20260702T233057Z_triton_rmsnorm_int8/

## 8. 业务落地准备

| 场景 | 完成情况 | 边界 |
|---|---|---|
| 智能客服 / 异步接入 | /jobs admission、Redis Stream、1000 QPS admission 压测 | 未接入真实业务用户流量 |
| 长文本处理 | 512K 历史 profile 与 40K 级 Week4 workload | 不作为常态 SLA |
| 代码助手 | 代码生成 E2E 与历史功能评测 | 不是完整 IDE 产品 |
| 多模态理解 | BAGEL 图文 API 与多案例验证 | 不是多副本生产级多模态平台 |

Week4 要求中对比开源竞品的完整横向竞品 benchmark 未作为最终已完成项表述。本项目完成的是 Seed-OSS 量化前后对照、历史代码生成评测和业务 workload E2E 验证。

## 9. 最终交付材料

| 材料 | 路径 |
|---|---|
| 最终交付主报告 | docs/week4_final_delivery_report.md |
| 最终系统验证矩阵 | docs/week4_system_validation_matrix.md |
| 简历逐句证据矩阵 | docs/week4_final_resume_evidence_matrix.md |
| Week3 阶段报告 | docs/week3_delivery_report.md |
| Week3 要求闭环 | docs/week3_requirement_closure.md |
| 架构说明 | docs/week3_architecture.md |
| 高可用部署 SOP | docs/week3_ha_deployment_sop.md |
| 运行与恢复 SOP | docs/week3_operations_sop.md |

Week4 要求中的系统演示视频和技术总结 PPT 未单独整理进仓库。本次最终交付以代码、运行脚本、证据目录、架构/SOP、验证矩阵和最终报告为主。

## 10. 最终结论

Week4 补齐了 Week3 反馈中最关键的共享熔断和真实主备验证问题，并完成 admission 压测、controlled OOM、真实 workload E2E、Triton A100 验证和最终文档整理。

系统满足 /jobs admission 场景下 1000 QPS、P95≤500ms、错误率≤1% 的验收指标。该指标的范围已经明确记录，不外推为完整 36B 模型生成的 1000 QPS SLA。
