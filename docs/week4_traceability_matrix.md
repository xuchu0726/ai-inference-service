# Week4 技术交付追踪矩阵

## 使用原则

本矩阵用于记录 Week4 技术交付中的能力项、实现依据、验证证据和边界说明。所有指标均只在对应实验协议、硬件环境、服务 profile 与 workload 下成立，不外推为所有场景的绝对能力。

---

## 1. Seed-OSS-36B、REST API、512K 与动态推理预算

### 交付结论
基于 Seed-OSS-36B 模型搭建工程验证级 AI 推理服务，封装 RESTful API、动态推理预算控制和 Prometheus / Grafana 可观测性。512K 超长上下文为历史 4×A100 profile 的近上限验证；Week4 TP=2 主备 profile 用于验证主备切换、队列、admission 和容错。

### 实现与证据
- FastAPI Gateway：`app/main.py`、`app/inference.py`、`app/backends/vllm_backend.py`
- 512K 近上限运行：
  - `results/week2_hardening/seed_oss_4xa100_512k_near_limit_summary_20260614.json`
- 主备切换、动态预算降级：
  - `evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/failover_response.json`
  - `evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/validation_summary.md`
- Prometheus / Grafana：
  - `docs/week2_requirement_compliance_matrix.md`
  - `deployment/week3_ha/monitoring/`

### 技术说明
512K 是历史 4×A100 长上下文 profile 的能力验证，真实请求达到 500K+ token。Week4 主备 TP=2 高可用 profile 使用较小 `max-model-len`，用于主备切换、队列和 admission 验证。

---

## 2. INT8/W8A8、显存降低与吞吐提升

### 交付结论
完成 W8A8 compressed-tensors serving 路线、动态 Batch 调度观察与 KV 缓存相关指标记录。模型加载显存占用降低 70% 以上，固定评测协议下吞吐提升可支撑 29% 的量化收益结论；plain INT8 / AWQ / GPTQ 不作为稳定 serving 完成项。

### 实现与证据
- W8A8 serving：
  - `deployment/cloud/`
  - `app/backends/vllm_backend.py`
- 量化性能报告：
  - `docs/week2_quantization_feasibility_report.md`
- 同协议 benchmark：
  - `results/new_2xa100_seed_oss_w8a8_batchprofile_concurrency_sweep_20260528_summary.csv`
- 真实队列与 KV 指标：
  - `evidence/week4_cloud/20260702T230508Z_real_primary_tp2_queue_kv_observation/`

### 已验证指标
- 模型加载显存：BF16 约 67.59 GiB，W8A8 约 17.71 GiB，降低约 73.8%。
- 同硬件、同 TP、同 workload/batch profile 下，W8A8 吞吐最低提升约 31.4%，支撑当前量化收益结论中的 29%。

### 技术说明
“推理速度提升 29%”指固定 benchmark protocol 下的服务吞吐或输出 token 吞吐改善，不代表任意输入、任意 batch、任意模型生成场景都固定提升 29%。

---

## 3. Dynamic Batch、KV Cache、PagedAttention、FlashAttention 与 GQA

### 交付结论
使用 vLLM runtime 提供的 PagedAttention、KV Cache 与 FlashAttention backend 能力，并记录 dynamic batching、queue、KV 指标和 GQA 机制说明。

### 实现与证据
- vLLM 运行参数：
  - `--max-num-batched-tokens`
  - `--max-num-seqs`
- 动态 batching / queue / KV 指标：
  - `evidence/week4_cloud/20260702T230508Z_real_primary_tp2_queue_kv_observation/`
- PagedAttention / KV Cache / GQA 文档：
  - `docs/week2_requirement_compliance_matrix.md`
  - `docs/continuous_batching_notes.md`
- 当前 4×A100 主备 TP=2 FlashAttention runtime：
  - `evidence/week4_cloud/20260703T004300Z_current_tp2_flashattn_runtime/`

### 技术说明
PagedAttention、KV Cache 与 FlashAttention 均来自 vLLM serving stack 的实际 runtime 能力。FlashAttention 由 vLLM backend selector 自动选择为 `FLASH_ATTN`；未手写 FlashAttention 算子，也未做 FlashAttention 与其他 backend 的独立对照实验。

---

## 4. BAGEL 图文联合推理

### 交付结论
接入 BAGEL 多模态 runtime，形成图文联合推理 API，并完成多案例接口级行为验证。

### 实现与证据
- 多模态 FastAPI：
  - `app/multimodal/service.py`
  - `app/multimodal/main.py`
- BAGEL 多案例 E2E：
  - `results/week3_bagel/bagel_multicase_audit_summary_20260623.json`
- BAGEL workload runner：
  - `scripts/week4_cloud/run_bagel_workload_manifest.py`

### 技术说明
图像通过 multipart 上传，经 FastAPI gateway 转发给 BAGEL Gradio runtime；记录请求成功率、延迟以及 GPU 采样指标。

---

## 5. Redis Stream、Triton RMSNorm-INT8

### 交付结论
基于 Redis Stream 完成异步请求队列调度；基于 Triton 实现独立 RMSNorm-INT8 microkernel，并完成 A100 correctness 与 microbenchmark 验证。

### 实现与证据
- Redis Stream job queue：
  - `app/`
  - `evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/real_job_final.json`
- Triton kernel：
  - `app/kernels/rmsnorm_int8.py`
  - `evidence/week4_cloud/20260702T233057Z_triton_rmsnorm_int8/`

### 技术说明
Redis Stream 用于异步 job admission 与状态流转。Triton RMSNorm-INT8 已在 A100 上完成正确性及 microbenchmark 验证；其加速结论属于独立 kernel microbenchmark，不等同于 vLLM 端到端吞吐提升。

---

## 6. 高可用架构、Nginx、HPA、熔断与降级

### 交付结论
部署 Kubernetes HPA 自动扩缩容与 Nginx 负载均衡，设计熔断重试及低预算推理降级容错机制。

### 实现与证据
- HPA / Nginx / monitoring：
  - `deployment/week3_ha/`
  - `docs/week3_ha_deployment_sop.md`
  - `docs/week3_architecture.md`
- 主备 failover：
  - `evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/`
- Redis shared breaker / controlled OOM：
  - `evidence/week4_resource_exhaustion/20260702T224556Z_shared_breaker_v2/`

### 技术说明
主 upstream 连续失败会触发 retry、circuit breaker 与 fallback；fallback 使用较低 thinking budget 保障有限可用性。HPA 验证的是 Gateway 层扩缩容，模型 serving 使用独立主备 TP=2 upstream。

---

## 7. JMeter / wrk、1000 QPS、P95 与错误率

### 交付结论
使用 JMeter/wrk 完成 100~1000 QPS 压力测试；1000 QPS 短任务接入 P95 ≤ 500ms、错误率 ≤ 1%。

### 实现与证据
- JMeter 100 / 500 / 1000 QPS：
  - `evidence/week4_cloud/20260703T001000Z_real_gateway_redis_admission_jmeter/`
- wrk admission saturation：
  - `evidence/week4_cloud/20260703T002438Z_wrk_real_gateway_admission/`

### 已验证指标
- JMeter 1000 QPS：
  - 实际约 1015.89 RPS
  - P95 约 5 ms
  - error rate 0%
- wrk：
  - 约 7627.65 RPS
  - P95 约 34.122 ms
  - connect/read/write/status errors 均为 0

### 技术说明
该指标是 `/jobs` Gateway admission SLO：包括请求校验、Redis Stream 入队和 HTTP 202 返回。worker 未启动，因此不代表 Seed-OSS-36B 在 1000 QPS 下的完整生成吞吐或端到端生成延迟。

---

## 8. 长文本、多模态、代码生成 E2E

### 交付结论
完成长文本、多模态、代码生成端到端压测。

### 实现与证据
- 长文本：
  - `evidence/week4_cloud/20260702_long_context_40960_profile/`
- 代码生成：
  - `evidence/week4_cloud/20260702_codegen_fixed_e2e/`
  - `evidence/week2_hardening/seed_oss_codegen_eval_20_result_evidence_20260614.txt`
- 多模态：
  - `results/week3_bagel/bagel_multicase_audit_summary_20260623.json`

### 技术说明
这些是按 workload 分别进行的真实 E2E 执行验证，记录成功状态、请求级 latency、tokens/s 或多模态响应结果；不应表述为三类 workload 都进行了 1000 QPS 模型生成压测。

---

## 9. OOM 与节点故障

### 交付结论
使用 controlled CUDA-OOM fault injection 与主推理 upstream 受控终止验证容错。

### 实现与证据
- Controlled CUDA-OOM：
  - `evidence/week4_resource_exhaustion/20260702T224556Z_shared_breaker_v2/`
- 主推理服务实例受控终止、fallback 与恢复：
  - `evidence/week4_cloud/20260702T221725Z_dual_tp2_gateway_failover/`

### 技术说明
OOM 是确定性 HTTP 500 CUDA-OOM fault injection，用于验证分类、Redis shared breaker、fallback 与恢复，不是物理 GPU 显存耗尽。节点宕机指主推理服务实例 / upstream 受控终止与 failover recovery，不是整台 GPU 主机掉电。

---

## 最终结论

本矩阵中的技术结论均有实现、测试或原始证据支撑。后续复盘和技术说明必须严格遵循本矩阵的指标口径和边界，不扩大实验结论。
