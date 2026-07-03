# 真实 Gateway wrk admission 饱和压测

## 验收对象
- 真实 `app.main` Gateway，Uvicorn 8 workers，监听 `127.0.0.1:18082`。
- Redis `127.0.0.1:16379` 的隔离 DB1。
- 请求入口为 `POST /jobs`，使用 `loadtest/wrk/jobs_admission.lua`。
- worker 未启动，因此测量的是 Gateway 校验与 Redis Stream 入队的 admission 饱和能力。

## 方法
- 工具：wrk。
- 参数：8 threads、200 connections、30 seconds、latency reporting。
- 该工具为闭环饱和压测；实际 Requests/sec 由结果决定，不等同于 JMeter 固定 QPS 测试。

## 边界
- 不代表 Seed-OSS-36B 端到端生成吞吐或生成延迟。
- 测试后仅清理隔离 Redis DB1，不影响生产 DB0。
