# Week4 Load Test Assets

本目录用于保存接入层与模型执行层的压力测试计划、运行脚本和证据采集工具。

## 测试分层

- `POST /jobs`：接入层 admission capacity；100 / 500 / 1000 QPS 指该层的请求接入能力。
- `POST /generate`：模型执行层；以受控并发记录端到端延迟、完成吞吐、tokens/s 和错误率。
- `collect/`：采集 Gateway metrics、Redis Stream / PEL 状态和运行时快照。
- `wrk/`：最大吞吐补充测试；不作为固定 100 / 500 / 1000 QPS 的唯一验收工具。
