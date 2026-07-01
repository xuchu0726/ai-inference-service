# Week4 云端执行边界

## RunPod GPU Pod 边界

RunPod GPU Pod 用于 GPU 模型服务、真实推理 workload、故障注入、Triton GPU microbenchmark、BAGEL benchmark 和 JMeter/wrk 压测。

Pod 内不依赖 Docker Compose，也不要求 Docker daemon。

## 代码生成功能评测协议

1. 云端 Gateway 对 `codegen_functional_50.jsonl` 生成响应。
2. 云端保存 `codegen_responses.jsonl`、请求级 metrics、环境快照和模型版本。
3. 将云端响应文件拉回本地。
4. 本地使用 Docker 隔离 evaluator 执行 50 个函数任务的断言。
5. 最终报告同时保存云端推理证据和本地功能断言结果。

该边界避免将 RunPod 容器能力误当作可用 Docker runtime，同时保留生成端与执行验证端的完整可追溯性。
