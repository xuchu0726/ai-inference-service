# Workload-Aware Routing Policy 抽象说明

## 1. 背景

Batch-Token 调优实验已经验证，不同 workload 对 max_num_batched_tokens 的最优选择并不相同。

在 short-output c8 burst 场景下，32768 profile 相比 8192 将 QPS 从 1.921 提升到 2.371，并将 P95 latency 从 7.350s 降低到 3.415s。

在 long-output c4 decode-heavy 场景下，8192 profile 更稳健，P95 latency 为 13.258s，而 32768 为 16.406s。

因此，推理服务不应把 max_num_batched_tokens 简化为单一固定最优参数，而应根据请求特征选择不同 serving profile。

## 2. 当前实现范围

当前新增 app/routing.py，用于将 batch-token 调优结论沉淀为轻量 workload-aware routing policy abstraction。

该模块根据以下请求特征判断 workload 类型：

| 特征 | 作用 |
|---|---|
| prompt_chars | 粗略判断输入长度和潜在 prefill 压力 |
| max_new_tokens | 判断请求是否偏 short-output 或 decode-heavy |
| concurrency_hint | 用于表达 burst 请求形态 |

当前支持两类 workload：

| Workload | 推荐 profile | max_num_batched_tokens |
|---|---|---:|
| short_output_burst | short_output_burst_32768 | 32768 |
| long_output_or_mixed | long_output_or_mixed_8192 | 8192 |

## 3. 工程边界

当前实现不是完整生产级 gateway routing，也没有启动多个 vLLM 实例。

当前实现只完成以下内容：

1. 将实测 batch-token tuning 结论抽象为可测试的 routing policy；
2. 用单元测试验证 short-output burst、long-output 和 long-context 输入能够选择预期 profile；
3. 为后续多 serving profile、网关路由、降级策略和高可用设计提供代码基础。

当前不声明以下能力已经完成：

1. 多 vLLM 实例部署；
2. 运行时真实流量路由；
3. 根据 Prometheus metrics 实时调度；
4. 生产级负载均衡；
5. 完整 gateway fallback。

## 4. 测试结果

已新增单元测试：

- tests/test_routing.py

测试覆盖：

1. high-concurrency short-output 请求选择 32768 profile；
2. long-output 请求选择 8192 profile；
3. long-context 请求选择 8192 profile。

测试结果：

    3 passed in 0.02s

Evidence：

- app/routing.py
- tests/test_routing.py
- logs/week2_routing_policy_initial_snapshot_20260527.txt
- logs/week2_routing_policy_test_snapshot_20260527.txt

## 5. 后续扩展方向

后续可以将该 policy 接入 API gateway 或 FastAPI 层，在真实多 profile serving 环境中选择不同 vLLM backend。

推荐扩展路线：

1. 启动多个 vLLM serving profile，例如 8192 profile 和 32768 profile；
2. 在 gateway 层根据请求特征选择目标 backend；
3. 接入 Prometheus metrics，用 running requests、waiting requests、KV cache usage 和 P95 latency 做更动态的路由决策；
4. 与 timeout、fallback、circuit breaker 和高可用设计结合。
