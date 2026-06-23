# Week3 要求闭环说明

## 1. 高并发设计

### 要求

部署负载均衡层，支持自动扩缩容。

### 完成情况

已完成。

- Nginx 负载均衡层；
- Kubernetes Service；
- Gateway 多副本；
- HPA 最小 2、副本最大 4；
- CPU 50% 扩缩容阈值；
- 实际 2 -> 4 -> 2 验证；
- Pod 故障恢复、反亲和与滚动更新证据。

证据目录：`evidence/week3_ha/`。

## 2. 容错机制

### 要求

实现请求超时重试、节点异常熔断和低预算推理降级。

### 完成情况

已完成。

- 主、fallback 后端超时均为 8 秒；
- 有界重试 1 次，退避 0.2 秒；
- 连续失败 2 次触发 process-local circuit breaker；
- 恢复窗口为 20 秒；
- fallback 使用 thinking budget 512；
- Prometheus 记录 retry、circuit state、circuit transition 和 fallback 指标；
- 已有 timeout retry、breaker、真实 HTTP failover、恢复与 Prometheus 证据。

边界：熔断器为 Gateway 进程本地状态，不是跨副本共享的分布式熔断状态。

## 3. BAGEL 多模态推理

### 要求

实现图像加文本推理、多模态 API，并验证可行性和资源占用。

### 完成情况

已完成。

- FastAPI `POST /multimodal/generate`；
- BAGEL-7B-MoT 图像理解 Runtime；
- RunPod HTTPS Proxy 暴露；
- 三个官方图像案例；
- 每案例 3 次，总计 9/9 成功；
- 延迟、GPU 显存、GPU 利用率原始 JSON/CSV；
- 人工核验与过度具体描述风险分析。

关键审计结果：

- meme：通过；
- octupusy：通过，主要体现 OCR 与图文联合理解；
- women：部分通过，局部白色图案被过度具体命名为“小狗刺绣”。

## 4. Grafana 监控

### 要求

展示延迟、错误和资源。

### 完成情况

已完成。

BAGEL Dashboard 已展示 Target Up、请求数、错误数、错误率、请求速率、P50/P95 latency、GPU memory 和 GPU utilization。

## 5. 高可用架构图与 SOP

### 要求

提供包含 Seed-OSS 和 BAGEL 的高可用架构图及 SOP。

### 完成情况

架构图源文件：`docs/diagrams/week3_architecture.mmd`。  
架构说明：`docs/week3_architecture.md`。  
操作 SOP：`docs/week3_operations_sop.md`。

## 6. 统一多模态表示说明

BAGEL 官方能力范围包含统一多模态理解和生成。项目当前实际接入的是图像理解路径：图像与文本请求通过 FastAPI 接口进入 BAGEL Runtime，服务返回文本理解结果。

项目未实现图像生成、图像编辑、统一多模态 agent、BAGEL 多副本 HA 或 BAGEL 接入文本 Nginx 网关。这些能力不得写成已完成。
