# Week3 Seed-OSS Gateway 高可用接入层与 BAGEL 单 Pod 多模态服务交付报告

## 1. 交付目标与范围

本阶段目标是完成 Seed-OSS 文本推理服务的高可用接入层、容错与低预算降级机制，并完成 BAGEL 图像加文本理解 API、资源观测和受控业务场景验证。

实际交付由两条独立数据路径组成：

1. Seed-OSS 文本推理高可用路径：Nginx、Kubernetes Service、Gateway 多副本、HPA、Primary/Fallback vLLM、Prometheus 和 Grafana；
2. BAGEL 图文理解路径：RunPod HTTPS Proxy、FastAPI、Gradio Client、BAGEL Runtime、Prometheus 和 Grafana。

两条路径共享项目级监控体系，但当前不是同一个统一网关服务。BAGEL 运行在单个 RunPod Pod 中，不属于 Kubernetes Gateway 的多副本数据平面。

### 可复现环境与测量边界

| 子系统 | 验证环境与版本/资源 | 测量边界 |
|---|---|---|
| Gateway HA | 本地 kind；`ai-inference-gateway:week3-resilience-v9`；初始 2 副本；CPU request=`100m`、limit=`500m`；memory request=`128Mi`、limit=`256Mi` | HPA 使用 MockBackend 与 CPU load generator，验证 Gateway 接入与路由层弹性，不验证 GPU vLLM 模型实例自动扩缩容 |
| Gateway HPA | `minReplicas=2`、`maxReplicas=4`、CPU target=`50%`；scale-down stabilization window=`60s` | HPA CPU utilisation 相对 Gateway Pod CPU request 计算，不是宿主机 CPU 或 GPU 利用率 |
| 真实 Primary | RunPod；Seed-OSS-36B-Instruct-W8A8；vLLM `0.23.0`；TP=2；`2 × A100-SXM4-80GB` | 用于 HTTPS、认证、模型发现与最小生成请求连通性验证，不作为性能 benchmark |
| BAGEL Runtime | RunPod 单 Pod；`ByteDance-Seed/BAGEL-7B-MoT`；Python `3.10.12`；Torch `2.5.1+cu124`；`1 × A100-SXM4-80GB` | 图像加文本到文本理解输出；不代表 BAGEL 多副本高可用或模型内部机制白盒验证 |
| 监控与资源采样 | Prometheus / Grafana；BAGEL 服务成功请求后更新 GPU Gauge；审计脚本每 `0.5s` 调用 `nvidia-smi` | Gauge 用于请求完成后的资源状态关联；审计峰值为采样窗口最大值，不是连续 profiler 全程轨迹 |

主要环境证据见 `deployment/week3_ha/k8s/gateway-deployment.yaml`、`deployment/week3_ha/k8s/local_hpa/gateway-hpa.yaml`、`evidence/week3_ha/real_primary/nginx_gateway_real_primary_success_20260623.txt`、`evidence/week3_bagel/bagel_runtime_environment_20260623.txt`。

## 2. 系统架构与组件边界

客户端请求先进入 Nginx 入口代理层；Nginx 将请求转发至 inference-gateway Kubernetes Service，再由 Kubernetes Service 对后端 Gateway Pod Endpoint 进行分发。Nginx 配置 `proxy_next_upstream off`，不执行 upstream retry；Gateway 统一负责 Primary/Fallback 路由、超时、重试、熔断和 fallback 决策，避免双层重试造成重复推理。

本地 kind 验证通过 `inference-nginx` Kubernetes Service 进入 Nginx，覆盖 Nginx Pod 优雅终止和 Gateway 后端路由。该验证不覆盖云负载均衡器、DNS failover 或跨可用区入口高可用。

Gateway 韧性参数如下：

| 参数 | 配置 |
|---|---:|
| Primary timeout | 8 秒 |
| Fallback timeout | 8 秒 |
| Bounded retry | 1 次 |
| Retry backoff | 0.2 秒 |
| Circuit-breaker failure threshold | 2 |
| Circuit-breaker recovery window | 20 秒 |
| Fallback thinking budget | 512 |
| HPA minimum replicas | 2 |
| HPA maximum replicas | 4 |
| HPA CPU target | 50% |

BAGEL 图文理解请求经 RunPod HTTPS Proxy 到达 FastAPI `:8000`。FastAPI 接收 multipart 图像文件与文本 prompt，再通过本地 Gradio Client 调用 BAGEL Runtime `:7860`。当前验证接口为：

- `GET /multimodal/health`
- `POST /multimodal/generate`
- `GET /metrics`

完整架构图见 `docs/diagrams/week3_architecture.mmd`，架构说明见 `docs/week3_architecture.md`。

## 3. 高并发、高可用与容错设计

Gateway Deployment 使用多副本、readiness/liveness probes 和滚动更新。HPA 以 Gateway Deployment 为目标，使用 CPU 平均利用率目标值 50% 计算期望副本数；在本次受控负载验证中，Gateway 从 2 个副本扩展至 4 个副本，并在负载结束和 60 秒 scale-down stabilization window 后回落至 2 个副本。

Gateway Deployment 配置了基于 `kubernetes.io/hostname` 的 `preferredDuringSchedulingIgnoredDuringExecution` 软反亲和策略。调度器会优先将带有 `app=inference-gateway` 标签的 Gateway 副本放置到不同节点；HPA 验证结束时，两个 Gateway Pod 实际分别运行在 `desktop-worker` 与 `desktop-worker2`。

该策略不是硬约束。当集群资源不足或仅有单节点时，Kubernetes 仍可能将副本放置到同一节点。因此，本项目不将其表述为严格的节点级副本隔离保证。

HPA 以 Gateway Deployment 为目标，使用 CPU 平均利用率目标值 50% 计算期望副本数。在受控 CPU load generator 下，Gateway CPU utilisation 从 `305%/50%` 上升至 `475%/50%`，副本数由 2 扩展至 4；负载结束后，经过 60 秒 scale-down stabilization window 回落至 2。这里的 CPU utilisation 相对于 Gateway Pod 配置的 CPU request（`100m`）计算，不是宿主机 CPU 使用率或 GPU 利用率。

该 HPA 验证使用本地 kind 集群、MockBackend 和 CPU load generator，验证的是服务接入与路由层弹性，不是 GPU vLLM 模型实例自动扩缩容。

Gateway 统一处理后端异常：Primary 超时后执行一次有界重试；连续失败达到阈值后进入 process-local circuit breaker；熔断打开后请求直接切换到 Fallback upstream，并固定使用 `thinking_budget=512`；恢复窗口结束后通过探测请求恢复 Primary 路由。

Circuit breaker 状态保存在单个 Gateway 进程内，不是 Redis、etcd 或数据库支持的跨副本共享熔断状态。本次验证证明应用层上游路由降级；不证明 Primary 与 Fallback 具备主机、GPU、网络或区域级故障域隔离。

## 4. 验证协议与结果总表

| 验证项 | 结果 | 关键指标与结论 | 主要证据 |
|---|---|---|---|
| Gateway HPA 扩缩容 | 通过 | 负载期间 CPU utilisation 相对 50% target 上升，HPA 随后将 Gateway 从 2 扩展至 4 副本；负载结束并经过 60 秒 scale-down stabilization window 后回落至 2 副本 | `evidence/week3_ha/hpa/hpa_scaleout_scalein_final_summary.txt` |
| Gateway Pod 删除恢复 | 通过 | 探针运行在未删除 Gateway Pod 内；删除前 `46/46` 成功，删除后 `299/299` 成功；新副本首次命中发生在删除后 7.608 秒。该结果证明 Service 可持续路由到幸存副本，不等价于公网客户端、真实 GPU vLLM 后端或生产网络条件下的零中断保证 | `evidence/week3_ha/failover/pod_delete_failover_20260621T232310Z_summary.txt`；`evidence/week3_ha/failover/pod_delete_failover_20260621T232310Z_metadata.txt` |
| Nginx 副本优雅终止 | 通过 | 初始终止测试为 `327/328` 成功，出现 1 次 `Connection refused`；增加 `preStop sleep 5` 与 `terminationGracePeriodSeconds=15` 后，三轮合计 `987/987` 成功。该结果仅覆盖本地 kind 测试协议，不构成生产零中断保证 | `evidence/week3_ha/nginx/failover_validation_summary.txt` |
| 真实 Primary 基线 | 通过 | Nginx → Gateway×2 → RunPod W8A8 Primary 的 `/readyz` 与一次短输出 `/generate` 均返回 HTTP 200；该请求输出 8 tokens，端到端 latency=0.874s，tokens/s=9.1483。该基线仅证明端到端连通性，不构成模型性能 benchmark | `evidence/week3_ha/real_primary/nginx_gateway_real_primary_success_20260623.txt`；`evidence/week3_ha/real_primary/public_primary_validation_20260623.txt` |
| 超时、重试、熔断、Fallback | 通过 | Primary 失败后请求切至 Fallback；首次两次请求 `primary_attempts=2`，熔断打开后后续请求 `primary_attempts=0`；Fallback budget=512 | `evidence/week3_ha/real_failover/timeout_fallback_breaker_20260623_143812.txt` |
| Primary 恢复 | 通过 | 恢复探测后返回 `route=primary`，breaker 从 half_open 回到 closed | `evidence/week3_ha/real_failover/primary_recovery_v9_20260623_144856.txt` |
| BAGEL 官方图文基线 | 通过 | 三案例审计前完成两轮独立 n=5 运行，均 `5/5` 成功，用于确认 Runtime、FastAPI 与 GPU 采样链路稳定 | `evidence/week3_bagel/bagel_understanding_n5_20260623T185745Z.txt`；`evidence/week3_bagel/bagel_understanding_n5_20260623T185952Z.txt` |
| BAGEL 官方图文案例 | 通过 | 三个案例、每例 3 次，共 `9/9` 成功；固定参数与 `do_sample=false` 下输出稳定 | `results/week3_bagel/bagel_multicase_audit_summary_20260623.csv` |
| 电商商品图文理解 | 服务可行性通过；内容约束遵循未通过 | `3/3` 成功；P50=3.878s、P95=3.926s 仅为 n=3 受控请求的描述性统计；benchmark 期间按 0.5 秒采样的最大 GPU 显存=29,773 MiB、GPU util=74%，不代表全程平均利用率或多并发饱和性能 | `results/week3_bagel/bagel_understanding_ecommerce_backpack_listing_n3_20260623T211551Z.json` |
| Gateway 回归与异常契约测试 | 通过 | 后端异常分类契约测试 `3 passed`；改动后回归 `11 passed`；Deployment rollout 与双 Pod ready smoke 通过 | `evidence/week3_ha/backend_resilience/backend_error_contract_tests.txt`；`evidence/week3_ha/backend_resilience/post_change_pytest.txt`；`evidence/week3_ha/backend_resilience/runtime_deployment_smoke.txt` |
| Grafana 与 Prometheus | 通过 | Gateway 与 BAGEL 指标均可查询；覆盖请求、错误、P50/P95、GPU memory、GPU utilization、retry、breaker 和 fallback | `evidence/week3_ha/monitoring/validation_summary.txt`；`evidence/week3_bagel/figures/grafana_bagel_multicase_audit_14_requests_20260623.png` |

## 5. BAGEL 图文联合理解与 API 验证

BAGEL 当前接入的是图像加文本到文本理解输出路径。客户端同时提交图像文件和文本 prompt，FastAPI 将两者转交给 BAGEL Runtime，服务返回图像描述、图中文字读取或商品文案草稿。

三案例人工审计结果如下：

| 案例 | 结论 | 支持证据与边界 |
|---|---|---|
| official_meme | 通过 | 正确识别三段式排版及考试手写内容变化；未完整描述末段线条细节，但不构成幻觉 |
| official_octupusy | 通过 | 主要验证 OCR 与图文联合理解；输出中的作品信息可由图中文字直接支持 |
| official_women | 部分通过 | 正确描述主体、服装和背景；将局部白色图案命名为“小狗刺绣”，属于过度具体描述风险 |

### 多模态 API 契约

BAGEL 服务提供 `GET /multimodal/health` 与 `POST /multimodal/generate`。健康检查会验证本地 Gradio Runtime 可达性；Runtime 不可用时返回 HTTP `503`。

`POST /multimodal/generate` 使用 multipart 请求，包含必填的 `image` 与 `prompt`，并支持 `show_thinking`、`do_sample`、`temperature` 和 `max_new_tokens` 参数。默认值分别为 `false`、`false`、`0.3` 和 `512`。

| 契约项 | 当前实现 |
|---|---|
| 图像类型 | JPEG、PNG、WEBP |
| 图片大小 | 最大 `10 MiB` |
| temperature | `[0.0, 2.0]` |
| max_new_tokens | `[1, 1024]` |
| 参数或输入错误 | 空 prompt / 空图像返回 `400`；不支持图像类型返回 `415`；非法 temperature 或 max_new_tokens 返回 `422`；图片过大返回 `413` |
| Runtime 超时 | HTTP `504` |
| Gradio / BAGEL 上游错误 | HTTP `502` |
| 成功响应 | `response`、`latency_seconds`、`backend`、`model_name`、`image_filename`、`image_bytes`、`max_new_tokens`、`temperature`、`show_thinking`、`do_sample` |

该契约使调用方能够区分参数错误、Runtime 超时与上游失败，并将成功、超时和上游错误纳入 Prometheus 请求与错误指标。

### 统一多模态表征的工程优势

BAGEL 的统一多模态能力在本项目中的工程价值是：同一服务接口可同时接收图像与文本，并在联合上下文下输出统一的理解结果。相比将 OCR、视觉分类、商品属性抽取和文本生成拆分为多个独立模型，这种统一接口设计可减少跨服务编排、接口转换和中间结果对齐的复杂度。

本项目未对多模型拼接方案进行成本、延迟或维护复杂度的定量对比。当前验证的是接口级联合输入能力：图像文件与文本 prompt 通过同一个多模态 API 进入 BAGEL Runtime，并返回图像描述、图中文字读取和商品文案草稿。该结论不代表已测量或复现 BAGEL 内部视觉 token、共享表征、MoT 路由或生成解码机制。

在三个官方受控样例和一个电商商品图样例中，服务能够处理图像主体、场景与图中文字相关输入，并在固定输入与 `do_sample=false` 条件下稳定返回结果。

## 6. 电商商品图文条件文案草稿场景

受控电商案例输入商品背包图片与文本约束，要求输出商品标题候选、可见卖点和不可确认信息提示。

三次请求均成功，且输出一致。P50=3.878 秒、P95=3.926 秒仅为 n=3 受控请求的描述性统计，不构成稳定性能 benchmark 或跨系统性能排名。模型能够生成商品文案草稿，但没有严格遵守“仅基于图片可见信息”的约束。“耐用材质”“适合户外使用”“彰显品质”“便于分类存放摄影器材”等表述无法仅从图像直接确认；“户外摄影包”也属于过度具体分类。

因此，该服务当前可用于生成商品标题和卖点草稿，不可直接自动发布。生产接入需要补充：

- 商品属性白名单；
- 结构化商品库校验；
- 风险词拦截；
- 人工复核；
- 对不可确认字段的显式标记。

人工审计见 `evidence/week3_bagel/ecommerce_backpack_manual_validation_20260623.md`。

商品图片二进制未提交到仓库；来源、许可、SHA256 和下载脚本见 `evidence/week3_bagel/ecommerce_backpack_source_and_license.md`。该样例仅用于非商业技术验证。

## 7. 监控与运维

Gateway 与 BAGEL FastAPI 均暴露 Prometheus 指标。

Gateway Resilience Dashboard 覆盖：

- Gateway Pod up；
- backend readiness；
- 请求速率；
- backend failure 分类；
- retry attempts；
- circuit-breaker state；
- circuit-breaker transition；
- fallback requests；
- fallback thinking budget。

BAGEL Multimodal Observability Dashboard 覆盖：

- Target Up；
- successful requests；
- recorded errors；
- error rate；
- request rate；
- P50/P95 Gateway-to-BAGEL latency；
- GPU memory；
- GPU utilization。

BAGEL benchmark 的 client latency 从本机向 FastAPI 发起请求开始计时，包含 FastAPI、Gradio Client 与 BAGEL 推理，不包含浏览器交互和 RunPod HTTPS Proxy 的公网网络开销。Benchmark 的 GPU memory 和 GPU utilization 由独立线程每 0.5 秒调用 `nvidia-smi` 采样，报告中的峰值为该采样窗口内的最大值。

Prometheus 中的 BAGEL GPU memory 与 GPU utilization Gauge 在成功请求后采样，用于关联请求完成后的服务侧资源状态；它们不是完整请求生命周期的连续 GPU profiler 轨迹。Grafana P50/P95 用于运行期趋势观察；在小样本或短时间窗口下，不用于定义生产 SLA，也不替代离线 benchmark 的原始 client latency 统计。

BAGEL Runtime 恢复、端口检查、日志定位和公网入口排障流程见 `docs/week3_operations_sop.md`。Seed-OSS 高可用推理栈部署、验收、回滚和证据保存流程见 `docs/week3_ha_deployment_sop.md`。

## 8. 已知边界与工程结论

本阶段完成了 Week3 要求的高可用接入层、服务容错、低预算降级、BAGEL 图文联合理解、资源观测、部署 SOP 和架构说明。

以下能力未实现，不得写成已完成：

- GPU vLLM 模型实例自动扩缩容；
- Kubernetes worker node 宕机或 GPU OOM 的真机演练；
- 跨副本共享的分布式熔断状态；
- BAGEL 多副本高可用；
- BAGEL 统一接入文本 Nginx Gateway；
- 图像生成、图像编辑、跨模态检索或多模态 agent；
- 带鉴权、限流和多租户隔离的生产级 BAGEL 公网服务；
- 模型内部统一多模态表征、视觉 token 或 MoT 路由的白盒验证。

工程上，当前结果证明了两件事：第一，Seed-OSS 文本推理路径可在多副本 Gateway、Nginx、HPA、retry、circuit breaker 和 Fallback 组合下完成可观测的服务韧性验证；第二，BAGEL 可以作为独立图文理解服务处理受控输入，但商品属性和局部视觉细节仍需外部校验与人工复核。

## 9. 交付与复现入口

正式主报告：

- `docs/week3_delivery_report.md`

架构与部署附件：

- `docs/week3_architecture.md`
- `docs/week3_ha_deployment_sop.md`
- `docs/week3_operations_sop.md`
- `docs/diagrams/week3_architecture.mmd`

要求逐条闭环附录：

- `docs/week3_requirement_closure.md`

关键证据目录：

- `evidence/week3_ha/`
- `evidence/week3_bagel/`
- `results/week3_ha/`
- `results/week3_bagel/`

关键验证脚本：

- `scripts/week3_ha/verify_deployment_stack.sh`
- `scripts/week3_ha/verify_fallback_http.py`
- `scripts/week3_ha/hpa_loadgen.py`
- `scripts/week3_ha/run_nginx_failover_probe.py`
- `scripts/week3_bagel/run_multicase_audit.sh`
- `scripts/week3_bagel/run_understanding_benchmark.py`
