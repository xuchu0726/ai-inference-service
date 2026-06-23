# Week3 运行与恢复 SOP

## BAGEL 恢复流程

1. 先检查 7860、8000 端口和 GPU 状态；已有进程不得直接覆盖。
2. 在 RunPod 仓库执行 `./scripts/week3_bagel/restore_bagel_stack.sh`。
3. 脚本依次启动 BAGEL Runtime:7860、等待 Runtime 就绪、启动 FastAPI:8000、等待 `/multimodal/health` 就绪。
4. 成功标准：`GET /multimodal/health` 返回 `status=ready`，且 `GET /metrics` 可读取指标。

## BAGEL 故障定位

- 8000 不可用：检查 `logs/week3_bagel/multimodal_api.log` 与端口监听状态。
- 7860 不可用：检查 `logs/week3_bagel/bagel_runtime.log` 与端口监听状态。
- GPU 异常：检查 `nvidia-smi`、显存占用和残留进程。
- 公网入口异常：先验证 Pod 内 `127.0.0.1:8000`，再验证 RunPod HTTPS proxy。

## 监控检查

- Prometheus 通过 `bagel-runpod` job 每 5 秒抓取 RunPod HTTPS `/metrics`。
- Grafana Dashboard：`Week3 BAGEL Multimodal Observability`。
- 核验 Target Up、成功请求、错误数、错误率、P50/P95 latency、GPU memory、GPU utilization。

## Seed-OSS Gateway 韧性检查

- 观察 retry、circuit breaker state、circuit transition、fallback requests 与 fallback thinking budget 指标。
- Nginx 不做 upstream retry；重试、熔断和低预算降级由 Gateway 统一执行。

## 安全与能力边界

- BAGEL 当前仅验证单 Pod 图像理解 API。
- 公网入口当前没有认证和限流，不是生产级公网服务。
- 不使用模型输出直接进行高风险视觉判断。
- 局部细节、身份、文本可读性不确定时，必须增加人工复核或结构化验证。
