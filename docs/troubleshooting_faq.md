# 故障排查手册 FAQ

## 1. 文档目的

本文档记录 Seed-OSS-36B-Instruct 推理服务在部署、启动、调用、监控和 benchmark 过程中可能遇到的常见问题、排查方式和处理建议。

本项目当前服务链路为：

    Client
    -> FastAPI /generate
    -> VLLMBackend
    -> vLLM OpenAI-compatible Server
    -> Seed-OSS-36B-Instruct
    -> GPU inference

本文档用于补充 Week1 交付中已经记录的问题，并为 Week2 性能优化、并发测试、长上下文测试和后续高可用部署提供故障排查依据。

---

## 2. 服务启动顺序检查

推荐启动顺序：

1. 激活 Python virtual environment；
2. 检查 GPU 是否可见；
3. 启动 vLLM OpenAI-compatible server；
4. 通过 `/v1/models` 检查 vLLM readiness；
5. 设置 FastAPI 环境变量；
6. 启动 FastAPI service；
7. 调用 `/health` 检查 FastAPI；
8. 调用 `/generate` 做端到端推理；
9. 调用 `/metrics` 检查 vLLM 和 FastAPI 指标；
10. 再开始 benchmark。

检查命令示例：

    nvidia-smi
    curl http://127.0.0.1:8002/v1/models
    curl http://127.0.0.1:8000/health
    curl http://127.0.0.1:8000/metrics
    curl http://127.0.0.1:8002/metrics

---

## 3. vLLM 端口被占用

### 现象

vLLM 启动失败，日志中出现端口绑定失败，或 `ss -ltnp` 显示目标端口已被占用。

### Week1 实际案例

默认计划使用 8001 端口，但该端口已被 nginx 占用。

### 排查命令

    ss -ltnp | grep -E ':8000|:8001|:8002|:8003'

### 处理方式

将 vLLM 端口改为未占用端口，例如 8002：

    VLLM_PORT=8002
    VLLM_BASE_URL=http://127.0.0.1:8002/v1

同时保证 FastAPI 环境变量中 `VLLM_BASE_URL` 与实际 vLLM 端口一致。

---

## 4. FastAPI /metrics 返回 404

### 现象

访问 FastAPI `/metrics` 返回 404。

### 原因

FastAPI 默认不会自动暴露 Prometheus metrics，需要显式接入 instrumentator。

### 处理方式

安装依赖：

    prometheus-fastapi-instrumentator

在 `app/main.py` 中接入：

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)

### 验证方式

    curl http://127.0.0.1:8000/metrics

应看到 HTTP 请求计数、请求耗时、请求大小和响应大小等指标。

---

## 5. vLLM server not reachable

### 现象

FastAPI `/generate` 返回 500，日志中出现：

    vLLM server is not reachable
    ConnectionRefusedError
    Connection refused

### 常见原因

1. vLLM 尚未完成模型加载；
2. vLLM 端口配置错误；
3. FastAPI 中 `VLLM_BASE_URL` 与 vLLM 实际端口不一致；
4. vLLM 进程已经退出；
5. 模型加载失败但 FastAPI 已启动。

### 排查步骤

1. 检查 vLLM 进程：

        ps aux | grep vllm | grep -v grep

2. 检查端口：

        ss -ltnp | grep -E ':8002|:8003'

3. 检查 readiness：

        curl http://127.0.0.1:8002/v1/models

4. 检查 FastAPI 环境变量：

        echo $VLLM_BASE_URL

### 处理建议

FastAPI 不应在 vLLM ready 前发送 `/generate` 请求。部署脚本应先轮询 `/v1/models`，确认 vLLM ready 后再启动 FastAPI 或开始压测。

---

## 6. Seed-OSS 模型加载慢

### 现象

vLLM 启动后长时间没有 ready。

### 常见原因

1. 模型权重较大；
2. 首次下载需要较长时间；
3. safetensors shard 加载耗时；
4. 磁盘或网络带宽限制；
5. HF cache 未命中。

### Week1 记录

Seed-OSS-36B-Instruct 权重缓存约 68GB，下载和加载都需要明显时间。

### 处理建议

1. 保留完整 vLLM 启动日志；
2. 区分 download time 和 load checkpoint time；
3. 后续复用模型缓存；
4. 不要在模型未 ready 时启动 benchmark；
5. 通过 `/v1/models` 判断服务是否可用。

---

## 7. CUDA / GPU 不可见

### 现象

PyTorch 或 vLLM 检测不到 GPU。

### 排查命令

    nvidia-smi

    python - <<'PY'
    import torch
    print(torch.cuda.is_available())
    print(torch.cuda.device_count())
    for i in range(torch.cuda.device_count()):
        print(i, torch.cuda.get_device_name(i))
    PY

### 常见原因

1. CUDA_VISIBLE_DEVICES 设置异常；
2. 容器没有挂载 GPU；
3. 驱动/CUDA/PyTorch 版本不匹配；
4. venv 中 torch 版本被替换；
5. HPC/PBS 环境中 GPU UUID 与 vLLM device id 解析不兼容。

### 处理建议

1. 先验证 `nvidia-smi`；
2. 再验证 PyTorch CUDA；
3. 最后验证 vLLM；
4. 如果是 PBS 环境，需要额外检查 `CUDA_VISIBLE_DEVICES`。

---

## 8. OOM / 显存不足

### 现象

模型加载或推理过程中出现 CUDA OOM，或 vLLM worker 退出。

### 常见触发条件

1. max_model_len 过大；
2. max_num_batched_tokens 过大；
3. concurrency 过高；
4. max_new_tokens 过大；
5. gpu_memory_utilization 设置过高；
6. batch 中请求长度差异过大；
7. 长上下文 prefill 显存压力过大。

### Week1 资源边界

在 BF16、TP=2、max_model_len=4096 下，Seed-OSS-36B-Instruct 稳定运行时每张 A100 80GB 显存占用约 75.8GB/80GB。

### 处理建议

优先降低：

    MAX_MODEL_LEN
    MAX_NUM_BATCHED_TOKENS
    max_new_tokens
    concurrency

再考虑增加：

    tensor_parallel_size
    GPU 数量

不要直接从 4K 跳到 512K full-context，应进行上下文长度梯度测试。

---

## 9. max_model_len exceeded

### 现象

请求失败，提示输入长度超过模型或 vLLM 配置允许的最大上下文长度。

### 原因

请求 token 数超过 vLLM 启动时设置的 `MAX_MODEL_LEN`。

### 处理方式

1. 降低输入长度；
2. 提高 `MAX_MODEL_LEN`；
3. 同时重新评估 KV Cache 显存需求；
4. 记录不同上下文长度下的显存、P95、tokens/s 和错误率。

---

## 10. benchmark 请求超时

### 现象

benchmark 脚本中请求失败，出现 timeout。

### 常见原因

1. vLLM 队列等待时间过长；
2. concurrency 设置过高；
3. 长上下文 prefill 时间过长；
4. max_new_tokens 太大；
5. FastAPI 或 vLLM timeout 设置过短。

### 处理建议

1. 增大 benchmark timeout；
2. 降低 concurrency；
3. 降低 max_new_tokens；
4. 分离短 prompt benchmark 和长上下文 benchmark；
5. 记录失败请求，不要删除失败样本。

---

## 11. benchmark CSV 写入失败

### 现象

请求均返回 200，但写入 CSV 时报错，例如：

    OSError: [Errno 5] Input/output error

### Week1 实际案例

concurrency=4 测试首次写入 results 目录时出现 I/O error，随后写入临时路径并保存 retry 结果。

### 处理方式

1. 保留失败日志；
2. 尝试写入 `/tmp`；
3. 再复制到 results；
4. 对比 retry 结果；
5. 在报告中说明异常和处理方式。

---

## 12. Thinking Budget 不生效

### 现象

请求中传入 `thinking_budget`，但模型输出未体现 thinking 相关结构。

### 排查步骤

1. 确认 FastAPI request body 中包含 `thinking_budget`；
2. 确认 `GenerateRequest` schema 支持该字段；
3. 确认 VLLMBackend 接收到该字段；
4. 确认 Seed-OSS 请求中包含：

        chat_template_kwargs.thinking_budget

5. 确认环境变量：

        VLLM_ENABLE_SEED_THINKING_BUDGET=true

6. 确认模型名包含 Seed-OSS 或已强制启用 Seed thinking budget。

### 判断标准

如果输出中出现以下字段，说明 Seed-OSS thinking 链路生效：

    <seed:think>
    <seed:cot_budget_reflect>

---

## 13. Prometheus 指标缺失

### 现象

`/metrics` 可访问，但没有目标指标。

### 排查方向

1. 是否访问了正确服务端口；
2. FastAPI `/metrics` 与 vLLM `/metrics` 是两个不同接口；
3. vLLM 指标只有在服务运行且有请求后才更有价值；
4. Grafana dashboard 的 Prometheus datasource 是否配置正确。

### 常用指标

vLLM:

    vllm:num_requests_running
    vllm:num_requests_waiting
    vllm:kv_cache_usage_perc
    vllm:prefix_cache_queries_total
    vllm:prefix_cache_hits_total

FastAPI:

    http_requests_total
    http_request_duration_seconds
    http_request_size_bytes
    http_response_size_bytes

---

## 14. Week2 压测前检查清单

开始 GPU benchmark 前必须确认：

1. vLLM `/v1/models` 返回正常；
2. FastAPI `/health` 返回正常；
3. FastAPI `/generate` smoke test 成功；
4. vLLM `/metrics` 可访问；
5. FastAPI `/metrics` 可访问；
6. `nvidia-smi` 正常；
7. 输出目录存在；
8. benchmark timeout 足够；
9. concurrency 从低到高逐步增加；
10. 长上下文从 4K/8K/16K/32K 逐步增加；
11. 所有失败样本保留到日志和 CSV。
