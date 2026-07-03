# 真实 Gateway + Redis Stream admission 压测

## 验收对象
- 真实 `app.main` Gateway，Uvicorn 8 workers，监听 `127.0.0.1:18082`。
- 真实 Seed-OSS-36B W8A8 TP=2 primary / fallback 配置。
- Redis `127.0.0.1:16379`，使用隔离 DB1 与独立 key prefix。
- Apache JMeter 5.6.3，入口为 `POST /jobs`，期望 HTTP 202。

## 结果
| 目标档位 | 实际 RPS | P95 | 错误率 |
|---|---:|---:|---:|
| 100 QPS | 103.21 | 3 ms | 0% |
| 500 QPS | 510.29 | 8 ms | 0% |
| 1000 QPS | 1015.89 | 5 ms | 0% |

## 结论
1000 QPS 短任务接入满足 P95 ≤ 500 ms、错误率 ≤ 1%。

## 边界
- worker 未启动；请求完成 Gateway 校验、Redis Stream 入队与 HTTP 202 返回。
- 本结果不代表 Seed-OSS-36B 的端到端生成吞吐或生成延迟。
- 每档保留 summary、JMX、命令状态、Redis backlog 与原始 JTL 的 SHA256。
- 原始 JTL 位于 Pod 本地 `/opt`，其路径已记录；仅清理隔离 Redis DB1，不影响生产 DB0。
