# 请求超时重试验证结论

## 验证目标

验证 Gateway 对推理后端超时的处理链路：

`BackendTimeoutError -> 有界重试一次 -> primary 成功返回 -> Prometheus 记录 backend_timeout`

## 最终有效验证

- 镜像版本：`ai-inference-gateway:week3-resilience-v4`
- 故障注入：`MOCK_FAILURE_SEQUENCE=timeout,success`
- 重试配置：`RESILIENCE_RETRY_ATTEMPTS=1`
- 熔断阈值：`RESILIENCE_FAILURE_THRESHOLD=3`
- 验证结果：
  - HTTP 返回 `200 OK`
  - 响应路由为 `primary`
  - `primary_attempts=2`
  - Prometheus 指标 `gateway_retry_attempts_total{reason="backend_timeout"}=1`

说明第一次调用被注入为超时，Gateway 将其识别为 `BackendTimeoutError` 后进行一次受限重试；第二次 primary 调用成功。指标标签按真实失败类型记录为 `backend_timeout`。

## 中间诊断记录

`diagnostics/` 保存实现修复过程中的中间结果：

- 初始实现未将 `BackendTimeoutError` 纳入 retry 条件，第一次请求直接返回 504。
- 后续实现虽已重试成功，但 retry 指标将所有失败硬编码为 `backend_unavailable`。
- 最终版本将异常对象传入指标回调，并区分 `backend_timeout` 与 `backend_unavailable`。

这些文件用于保留修复过程，不作为最终通过证据。
