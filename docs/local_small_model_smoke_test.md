# 本地小模型推理 Smoke Test

## 1. 测试目的

本次测试用于验证本地环境是否能够运行真实开源语言模型，并完成最小 LLM 推理链路：

```text
model download → tokenizer → model.generate → decode → latency / tokens/s
```

该测试是从 mock backend 进入真实 TransformersBackend 前的准备步骤。

当前项目已经完成 FastAPI mock 推理服务、thinking_budget 参数传递、benchmark CSV 结果保存和可插拔 backend 初始架构。本次测试的目标是确认本地机器可以承载一个轻量级真实语言模型，为后续接入真实模型后端打基础。

---

## 2. 测试环境

```text
本地设备：Apple M4
内存：24GB
推理设备：MPS
Python 环境：conda base
推理框架：PyTorch + Transformers
测试模型：Qwen/Qwen2.5-0.5B-Instruct
```

---

## 3. 测试模型选择

本次选择 `Qwen/Qwen2.5-0.5B-Instruct` 作为本地 smoke test 模型。

选择原因：

- 参数规模较小，适合本地 Mac M4 + 24GB 内存环境。
- 支持 Hugging Face Transformers 加载。
- 可以验证真实 tokenizer、model.generate 和 decode 链路。
- 后续可以平滑封装为 `TransformersBackend`。
- 相比直接尝试 Seed-OSS-36B，该模型更适合作为本地工程链路验证模型。

本次测试不追求模型能力上限，重点是验证真实推理链路是否可运行。

---

## 4. 测试脚本

测试脚本位置：

```text
scripts/test_small_model.py
```

测试脚本完成以下步骤：

```text
1. 检查本地可用推理设备
2. 加载 Qwen/Qwen2.5-0.5B-Instruct tokenizer
3. 加载 Qwen/Qwen2.5-0.5B-Instruct model
4. 将模型移动到 MPS 设备
5. 构造 chat-style prompt
6. 执行 model.generate
7. 解码模型输出
8. 记录 input tokens、output tokens、生成延迟和 tokens/s
```

---

## 5. 测试输入

测试 prompt：

```text
请用三句话解释什么是大模型推理。
```

system prompt：

```text
你是一个简洁、专业的 AI 推理工程助手。
```

---

## 6. 测试结果

本地模型加载成功。

```text
Using device: mps
Loading model: Qwen/Qwen2.5-0.5B-Instruct
Model loaded in 66.14s
```

推理输出成功。

```text
Response:
大模型推理是一种通过深度学习技术训练的计算机程序，能够理解和执行复杂的任务和决策过程。它利用大量数据进行特征提取和模式识别，从而实现对大规模信息的处理和分析。这种推理方式在自然语言处理、图像识别、语音识别等领域有着广泛的应用前景。
```

性能指标：

```text
Input tokens: 35
Output tokens: 63
Generate latency: 4.67s
Tokens/s: 13.49
```

---

## 7. 当前结论

本地 Apple M4 + 24GB 内存环境可以运行 0.5B 级别真实语言模型，并完成基础文本生成任务。

本次测试说明当前本地环境已经具备以下能力：

```text
1. 下载并加载 Hugging Face 模型
2. 使用 tokenizer 构造模型输入
3. 使用 model.generate 执行真实推理
4. 使用 MPS 进行本地加速
5. 解码模型输出
6. 记录 input tokens、output tokens、latency 和 tokens/s
```

这意味着项目已经具备从 mock backend 进入真实 TransformersBackend 的基础条件。

---

## 8. 当前限制

本次测试仍然存在以下限制：

```text
1. 只测试了单条 prompt
2. 只测试了单轮 generation
3. 没有接入 FastAPI 服务
4. 没有接入 benchmark CSV 流程
5. 没有统计 P50 / P95 latency
6. 没有测试并发请求
7. 没有测试不同 context length
8. 没有测试 GPU memory / MPS memory 占用
9. 没有测试量化
10. 没有测试 vLLM 或 Seed-OSS
```

因此，该测试只能证明本地真实模型推理链路可运行，不能代表最终推理服务性能。

---

## 9. 后续计划

下一步将把本次 smoke test 中验证成功的真实推理逻辑封装进：

```text
app/backends/transformers_backend.py
```

目标是将服务链路升级为：

```text
POST /generate
→ FastAPI
→ inference.py
→ TransformersBackend
→ tokenizer
→ model.generate
→ decode
→ API response
→ benchmark CSV
```

后续 benchmark 将继续记录：

```text
input_tokens
output_tokens
generate_latency
tokens/s
backend
thinking_budget
```

这一步完成后，项目将从 mock 推理服务升级为真实 LLM inference service prototype。

---

## 10. 与 PTA 任务书的对应关系

本次测试对应 PTA 第 1 周中的以下任务：

```text
1. 环境配置
2. 加载模型并验证基础推理能力
3. 验证文本生成能力
4. 记录模型加载和推理过程中的基础性能数据
```

由于本地硬件无法直接运行 Seed-OSS-36B，本阶段先使用轻量级开源模型验证完整工程链路。后续在 CX3、Colab 或云 GPU 环境中，再尝试更大模型、vLLM 后端和 Seed-OSS 可行性实验。

---

## 11. 与求职目标的对应关系

本次测试为 AI 推理 / AI Infra 求职项目补充了第一项真实模型证据：

```text
从 mock API 进入真实 LLM 推理链路。
```

它为后续能力建设打基础：

```text
1. TransformersBackend
2. token-level benchmark
3. tokens/s 统计
4. P50 / P95 latency
5. 并发压测
6. GPU / CX3 实验
7. vLLM serving
8. KV Cache / batch / quantization 分析
```

最终目标不是停留在小模型，而是通过小模型先打通服务链路，再迁移到更接近工业推理场景的 vLLM、GPU 和大模型实验。