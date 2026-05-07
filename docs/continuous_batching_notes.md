# Continuous Batching 调度模拟说明

## 1. 文档目的

本文档记录本项目中 Continuous Batching 调度模拟实验的目的、方法、边界和结果解释。

该实验对应脚本：

    scripts/scheduler_simulation.py

该脚本用于模拟 LLM 在线推理服务中多个请求动态到达时，Static Batching 与 Continuous Batching 两种调度策略在等待时间、完成时间、尾延迟和 GPU 利用率上的差异。

重要说明：

    本实验是简化调度模拟，不是真实 vLLM/GPU benchmark。
    本实验不下载模型、不启动 vLLM、不调用 FastAPI、不执行真实大模型推理。
    真实服务性能需要通过 scripts/benchmark_vllm_backend.py 在 GPU 环境中测量。

---

## 2. 为什么需要这个模拟实验

大模型推理服务不是单个用户请求串行执行的问题，而是多个用户请求在同一时间段内不断到达、排队、进入 batch、生成 token、完成并返回的问题。

真实在线推理场景具有以下特点：

1. 请求到达时间不同
2. prompt 长度不同
3. output token 长度不同
4. 有些请求很短，有些请求很长
5. GPU 需要尽量保持高利用率
6. 服务需要同时关注吞吐和尾延迟

如果调度策略不合理，会出现：

1. 短请求被长请求拖慢
2. 新请求长时间排队
3. batch slot 空置
4. GPU idle gap 增加
5. P95 latency 变差
6. tokens/s 下降

因此，调度策略是 LLM serving 系统的重要组成部分。

---

## 3. Static Batching

Static Batching 可以理解为固定批处理。

简化规则：

1. 请求按照批次进入 GPU
2. 一个 batch 内的请求一起处理
3. 一批完成后再处理下一批
4. batch 内短请求可能需要等待最长请求完成

问题：

1. 短请求容易被长请求拖慢
2. 当前 batch 未结束时，新请求不能及时加入
3. batch slot 利用率不稳定
4. 尾延迟容易变高

在 LLM 推理中，输出 token 长度差异会放大该问题。

例如：

    Request A 输出 20 tokens
    Request B 输出 30 tokens
    Request C 输出 180 tokens
    Request D 输出 220 tokens

如果它们被静态绑定在一个 batch 中，短请求会受到长请求影响，服务整体响应时间变差。

---

## 4. Continuous Batching

Continuous Batching 可以理解为动态连续批处理。

简化规则：

1. GPU 维护一个 active request set
2. 每个 decode step 后检查请求是否完成
3. 完成的请求立即移除
4. 等待队列中的新请求补入空位
5. GPU 尽量持续处理活跃请求

优势：

1. 已完成请求可以及时返回
2. 新请求可以更快进入执行
3. batch slot 空置时间减少
4. GPU idle time 减少
5. 系统吞吐潜力提高
6. P95 latency 更容易改善

这也是 vLLM 等推理框架适合在线 serving 的关键原因之一。

---

## 5. 与 vLLM 的关系

vLLM 的核心优势包括：

1. Continuous Batching
2. PagedAttention
3. 高效 KV Cache 管理
4. OpenAI-compatible serving
5. GPU serving 优化

本项目主线仍然是使用 vLLM 作为真实推理引擎：

    FastAPI
    -> VLLMBackend
    -> vLLM
    -> GPU model
    -> benchmark

scheduler_simulation.py 不替代 vLLM，也不是自研 vLLM。

它的作用是：

1. 帮助解释 Continuous Batching 的工程动机
2. 辅助理解 vLLM 为什么适合高并发推理服务
3. 为第 2 周动态 batch 调度与 KV Cache 优化文档做铺垫
4. 在本地无 GPU 时补充 AI Infra 方向的系统理解证据

---

## 6. 与 PagedAttention 的关系

Continuous Batching 解决的是请求调度问题。

PagedAttention 解决的是 KV Cache 显存管理问题。

LLM 推理中，每个请求都会保存历史 token 的 Key/Value cache。高并发和长上下文会导致 KV Cache 占用大量显存。

PagedAttention 的思想类似操作系统分页：

1. 将 KV Cache 分成 block/page 管理
2. 按需分配和释放
3. 减少连续显存分配压力
4. 降低显存碎片和浪费
5. 支持更多并发请求和更长上下文

Continuous Batching 与 PagedAttention 是互补关系：

    Continuous Batching 让更多请求动态进入 active batch。
    PagedAttention 让这些请求的 KV Cache 更高效地被管理。

---

## 7. 模拟实验设计

脚本会生成一组虚拟请求。

每个请求包含：

1. request_id
2. arrival_time
3. prompt_tokens
4. output_tokens

默认配置：

1. num_requests = 64
2. avg_interarrival = 0.08
3. batch_size = 8
4. min_prompt_tokens = 32
5. max_prompt_tokens = 1024
6. min_output_tokens = 16
7. max_output_tokens = 256

这些请求不是来自真实 tokenizer，也不是模型真实输出，而是用于调度模拟的 synthetic workload。

---

## 8. 输出文件

默认输出：

    results/scheduler_requests.csv
    results/scheduler_simulation.csv
    results/scheduler_simulation_summary.csv

含义：

1. scheduler_requests.csv
   记录生成的虚拟请求。

2. scheduler_simulation.csv
   记录每个请求在不同策略下的 start_time、finish_time、wait_time 和 latency。

3. scheduler_simulation_summary.csv
   记录两种策略的汇总指标。

注意：

    这些结果是模拟数据，不是生产 benchmark 数据。
    不应将其写成 vLLM 实测性能结果。
    真实 vLLM 性能应由 results/vllm_backend_benchmark.csv 和 results/vllm_backend_benchmark_summary.csv 表示。

---

## 9. 当前模拟结果

在默认参数下，模拟结果如下。

Static Batching:

    avg_wait_time = 6.741794
    p50_wait_time = 6.5828
    p95_wait_time = 13.857835
    avg_latency = 9.306294
    p50_latency = 9.1608
    p95_latency = 16.565035
    gpu_idle_time = 0.5419
    gpu_utilization = 0.974266
    output_tokens_per_time = 446.958149

Continuous Batching:

    avg_wait_time = 4.526095
    p50_wait_time = 4.36518
    p95_wait_time = 9.618931
    avg_latency = 6.378265
    p50_latency = 6.31606
    p95_latency = 11.164498
    gpu_idle_time = 0.0816
    gpu_utilization = 0.994749
    output_tokens_per_time = 605.664365

---

## 10. 结果解释

在该简化模拟设定下，Continuous Batching 相比 Static Batching 表现出：

1. 更低的平均等待时间
2. 更低的 P95 等待时间
3. 更低的平均 latency
4. 更低的 P95 latency
5. 更少的 GPU idle time
6. 更高的 output_tokens_per_time

原因是：

    Static Batching 以固定 batch 为单位推进，请求之间绑定更强。
    Continuous Batching 可以在请求完成后释放 slot，并让新请求补入 active set。
    因此 Continuous Batching 更适合请求动态到达、输出长度差异明显的在线推理场景。

---

## 11. 实验边界

本实验不能证明：

1. vLLM 真实吞吐提升比例
2. Seed-OSS-36B 真实 latency
3. 云 GPU 上真实 tokens/s
4. 真实 PagedAttention 显存节省比例
5. 真实生产环境下的 QPS 上限

本实验可以说明：

1. Static Batching 和 Continuous Batching 的基本调度差异
2. 在线请求动态到达时，动态补位为什么有意义
3. vLLM 采用 Continuous Batching 的工程动机
4. 为什么 LLM serving 需要专门的调度系统

---

## 12. 与 项目任务的对应关系

项目 第 2 周要求包含：

1. 动态 Batch 调度
2. 平衡吞吐量与延迟
3. KV Cache 优化
4. Seed 模型特性深度应用
5. 性能优化报告

本模拟实验对应：

1. 动态 batch 调度的原理解释
2. Static Batching 与 Continuous Batching 的机制对比
3. vLLM serving 框架选择理由
4. 后续 KV Cache / PagedAttention 文档的铺垫

---

## 13. 与求职目标的关系

该模块增强 AI 推理 / AI Infra 项目的系统深度。

它证明项目不只是：

    调用一个模型 API

而是进一步关注：

1. 在线推理服务调度
2. 多请求并发
3. batch slot 利用率
4. P95 latency
5. throughput potential
6. vLLM 底层机制理解
7. benchmark 与 simulation 的边界区分

这有助于在面试中解释：

    为什么选择 vLLM？
    Continuous Batching 解决什么问题？
    Static Batching 的瓶颈是什么？
    PagedAttention 与 KV Cache 管理有什么关系？
    simulation 和真实 benchmark 有什么区别？

---

## 14. 下一步

后续工作：

1. 在云 GPU 上运行真实 vLLMBackend benchmark
2. 将真实结果写入 docs/vllm_benchmark_report.md
3. 增加 streaming benchmark，统计 TTFT / TPOT / ITL
4. 接入 Prometheus metrics
5. 在 Seed-OSS-36B 部署时继续分析 batch、KV Cache 和显存瓶颈
