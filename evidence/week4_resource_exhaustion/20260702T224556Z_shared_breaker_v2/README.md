# 受控资源耗尽与Redis共享熔断恢复验证

## 结论
- validation_passed=true。
- resource_exhausted_fallback：primary 返回确定性 HTTP 500 CUDA-OOM fault，Gateway 切换 fallback。
- breaker_open_fallback：Redis circuit 已打开，后续请求跳过 primary。
- primary_recovered_cross_gateway：新的 Gateway 读取同一 Redis breaker state，在 cooldown 后成功探测新的 success-primary，并恢复 primary 路由。

## 架构边界
- 本实验使用 mock upstream 注入“CUDA out of memory”HTTP 500。
- 它证明错误分类、Redis shared circuit breaker、fallback 与跨 Gateway recovery。
- 它不等同于真实 GPU 显存或 KV Cache OOM。
- 所有运行期日志和临时 Redis 数据放在 /opt；归档后复制到本目录。
