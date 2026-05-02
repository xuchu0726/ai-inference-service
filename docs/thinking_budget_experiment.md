# Thinking Budget 实验说明

## 1. 实验目的

本实验用于验证 `thinking_budget` 参数是否能够通过 FastAPI 推理接口传入后端，并被 benchmark 脚本记录下来。

当前阶段使用的是 mock 推理后端，因此该实验暂时不代表真实大模型的生成性能。它的主要作用是先搭建可复用的实验框架，后续接入真实模型、vLLM 或 Seed-OSS 后，可以继续复用同一套 benchmark 流程。

## 2. 当前实验环境

- 服务框架：FastAPI
- 接口：POST /generate
- 当前后端：mock backend
- 压测脚本：scripts/benchmark.py
- 结果文件：results/thinking_budget_benchmark.csv

## 3. 实验变量

本次实验测试 4 组 thinking_budget：

```text
0, 128, 512, 1024