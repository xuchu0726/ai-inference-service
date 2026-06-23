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

## 6. 统一多模态表示：项目级解释与验证边界

BAGEL 的统一多模态能力在项目中以联合输入接口体现：客户端同时提交图像文件和文本 prompt，FastAPI 将两者转交给 BAGEL Runtime，模型基于二者的联合条件生成文本结果。三案例中的雕塑说明牌读取表明，服务能够同时利用视觉主体与图中文字；人物图像案例则体现了基于视觉内容的文本描述。

本项目验证的是接口级图文联合理解行为，而不是对 BAGEL 内部视觉 token、共享表示、MoT 路由或生成解码机制的白盒验证。当前服务未暴露或测量这些内部表示，因此不得将其写成已完成的模型内部机制复现。

工程边界：当前接入仅覆盖图像加文本到文本理解输出，不覆盖图像生成、图像编辑、跨模态检索、统一多模态 agent 或 BAGEL 多副本高可用。

## 7. 电商商品图文生成场景与技术难点

新增受控电商商品图案例：商品图片与文本约束共同输入 BAGEL，要求输出商品标题、可见卖点和不可确认信息。

运行结果：3/3 成功；P50 为 3.878 秒，P95 为 3.926 秒，峰值显存为 29773 MiB，峰值 GPU 利用率为 74%。

质量结论：模型输出稳定，但未严格遵守“仅基于图片可见信息”的约束。“耐用材质”“适合户外使用”“彰显品质”“便于分类存放摄影器材”等内容无法仅通过图片确认。

工程结论：该服务可用于生成商品文案草稿，不可直接自动发布。生产接入应增加商品属性白名单、结构化商品库校验、风险词拦截和人工复核。

相关证据：
- `evidence/week3_bagel/ecommerce_backpack_manual_validation_20260623.md`
- `results/week3_bagel/bagel_understanding_ecommerce_backpack_listing_n3_20260623T211551Z.json`
- `evidence/week3_bagel/ecommerce_backpack_source_and_license.md`

### 统一多模态表征的工程优势

统一多模态表征的工程价值在于：同一模型服务能够同时接收图像与文本，并在联合上下文中输出统一的理解结果。相比将 OCR、视觉分类、商品属性抽取和文本生成拆分为多个独立模型，统一模型减少了跨服务编排、接口转换和中间结果对齐的复杂度。

本项目验证了这一优势在服务接口层的可用性：图像和文本 prompt 通过同一个多模态 API 进入 BAGEL Runtime，并返回面向图像描述、图中文字读取和商品文案草稿的文本结果。该结论仅覆盖接口级联合理解能力；不代表已复现或测量 BAGEL 内部视觉 token、共享表征、MoT 路由或生成解码机制。
