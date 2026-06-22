# 本机真实 HTTP 双 upstream 容错验证结论

## 验证目标

验证 Gateway 在真实 HTTP 网络路径下完成：

`primary timeout -> 有界重试 -> 熔断打开 -> 独立 fallback 接管 -> 低预算请求`

## 验证方式

测试启动两个独立的本机 HTTP 服务：

- primary：收到请求后延迟响应，使 Gateway 的 urllib 请求超时。
- fallback：接收 Gateway 转发的 OpenAI-compatible chat completion 请求并记录请求体。
- Gateway primary 与 fallback 分别指向不同的 loopback URL。

## 通过结果

- 第一个请求：primary 超时；Gateway 重试一次；第二次超时后 breaker 进入 open；请求切换到 fallback；返回 `route=fallback`、`primary_attempts=2`、`fallback_thinking_budget=512`。
- 第二个请求：breaker 已打开；不再访问 primary；直接切换到 fallback；`primary_attempts=0`。
- fallback 实际收到的请求体包含：

```json
{
  "chat_template_kwargs": {
    "thinking_budget": 512
  }
}
```

## 结论

本机已验证真实 HTTP 网络路径中的 timeout、retry、circuit breaker、独立 fallback endpoint 和 Seed-OSS 低预算请求序列化逻辑。

该验证使用轻量 HTTP test server，不代表真实 GPU/vLLM 服务性能或模型行为；真实 GPU 环境仍需验证独立 Seed-OSS vLLM 服务故障后的切换。