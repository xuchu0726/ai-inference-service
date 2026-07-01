# Week4 代码生成功能评测说明

## 评测目标

本评测将模型返回的代码与请求性能分离：模型服务负责生成与记录请求级指标；评测器在 Docker 隔离环境中执行固定断言，输出任务级功能结果。

## 输入与输出

- 输入：冻结的 `codegen_functional_50.jsonl` 与按 `case_id` 对齐的模型响应 JSONL。
- 输出：每题的 `passed`、`syntax_error`、`test_failed`、`timeout`、`runtime_error`、`import_error` 或 `missing_response`，并保存代码哈希、提取后的代码、stdout、stderr 与执行耗时。

## 隔离执行边界

- Docker 网络关闭：`network=none`。
- 只读根文件系统与只读工作目录。
- 临时目录限制为 32 MiB，内存限制 256 MiB，CPU 限制 0.5，进程数限制 64。
- 移除 Linux capabilities，启用 `no-new-privileges`，以非 root 用户执行。
- 宿主机超时后强制删除对应容器，避免残留进程。

## 结果解释边界

- 该任务集是冻结的轻量级 Python 函数与本地断言集合，不等同于官方 HumanEval 或 MBPP。
- 通过率必须与模型服务性能指标分开报告。
- Seed 与 Qwen 对照必须使用相同 manifest、prompt、tests、生成参数和隔离执行条件。
