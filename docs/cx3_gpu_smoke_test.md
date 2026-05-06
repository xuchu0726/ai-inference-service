# CX3 GPU 环境验证记录

## 1. 文档目的

本文档记录本项目在 Imperial CX3 上进行 GPU 环境验证的结果。

本次测试的目的不是直接运行 Seed-OSS-36B，也不是进行大模型性能压测，而是先确认以下基础条件是否成立：

1. 是否能够通过 PBS 作业系统申请到 GPU 计算节点
2. 是否能够看到 NVIDIA GPU
3. GPU 型号和显存是多少
4. CUDA 驱动是否可见
5. CX3 上是否有可用的 PyTorch + CUDA 环境
6. PyTorch 是否能够识别 CUDA GPU
7. 是否能够在 GPU 上完成最小张量计算

这一步对应第一周任务中的：

- 部署 GPU 环境
- 安装 / 验证 PyTorch 等依赖
- 记录并解决模型加载、依赖冲突等环境问题
- 编写环境配置指南

---

## 2. 作业提交方式

本次测试通过 PBS 作业系统提交，而不是在 login 节点直接运行。

使用的 PBS 脚本为：

    deployment/cx3_gpu_smoke.pbs

提交命令为：

    qsub deployment/cx3_gpu_smoke.pbs

作业配置如下：

| 配置项 | 内容 |
|---|---|
| Queue | v1_gpu72 |
| Nodes | 1 |
| GPUs | 1 |
| CPU cores | 4 |
| Memory | 64GB |
| Walltime | 00:30:00 |
| Job name | ai_inference_gpu_smoke |

---

## 3. 计算节点信息

本次作业成功运行在 CX3 GPU 计算节点上：

    Host: cx3-20-3

这说明测试不是在 login 节点运行，而是通过 PBS 正确分配到了计算节点。

---

## 4. GPU 信息

nvidia-smi 输出显示，本次作业分配到的 GPU 为：

    GPU: NVIDIA L40S
    Driver Version: 580.82.07
    CUDA Version reported by nvidia-smi: 13.0
    Visible GPU memory: 46068 MiB

PyTorch 进一步识别到：

    GPU 0 name: NVIDIA L40S
    GPU 0 total memory: 44.39 GB
    CUDA free memory before test: 43.97 GB
    CUDA free memory after test: 43.89 GB

因此，本次 CX3 GPU smoke test 确认当前可用 GPU 为单张 NVIDIA L40S，PyTorch 可见显存约为 44.39GB。

---

## 5. 软件环境

PBS 脚本中加载了以下关键模块：

    module purge
    module load tools/prod
    module load PyTorch/2.1.2-foss-2023a-CUDA-12.1.1

加载后，Python 和 PyTorch 环境如下：

    Python: 3.11.3
    PyTorch: 2.1.2
    PyTorch CUDA version: 12.1
    CUDA available from PyTorch: True
    CUDA device count: 1

这说明 CX3 上已经存在可用的 PyTorch + CUDA module，不需要在第一阶段自行安装 conda 或手动安装 PyTorch。

---

## 6. GPU 计算验证

测试脚本执行了一个最小 GPU 矩阵乘法：

    x = torch.randn((2048, 2048), device="cuda:0")
    y = torch.randn((2048, 2048), device="cuda:0")
    z = x @ y

执行结果：

    matmul shape: (2048, 2048)
    GPU matmul: OK

这说明 PyTorch 不仅能看到 CUDA GPU，而且能够在 GPU 上分配张量并执行实际计算。

---

## 7. 测试结果汇总

| 检查项 | 结果 |
|---|---|
| PBS 作业提交 | 成功 |
| GPU 计算节点分配 | 成功 |
| 运行节点 | cx3-20-3 |
| NVIDIA GPU 可见 | 成功 |
| GPU 型号 | NVIDIA L40S |
| GPU 显存 | 约 44.39GB |
| NVIDIA driver | 580.82.07 |
| nvidia-smi CUDA version | 13.0 |
| Loaded CUDA module | CUDA 12.1.1 |
| Python version | 3.11.3 |
| PyTorch version | 2.1.2 |
| PyTorch CUDA version | 12.1 |
| torch.cuda.is_available() | True |
| CUDA tensor allocation | 成功 |
| GPU matrix multiplication | 成功 |

---

## 8. 对 Seed-OSS-36B 部署的影响

本次测试确认当前可以使用单张 NVIDIA L40S GPU，PyTorch 可见显存约为 44.39GB。

Seed-OSS-36B 是 36B 参数规模的大模型。如果使用 BF16 或 FP16 精度，仅模型权重的粗略显存需求为：

    36B parameters × 2 bytes ≈ 72GB

这还没有包括：

1. KV Cache
2. Runtime overhead
3. Activation buffer
4. Framework overhead
5. Long-context memory cost
6. Batch / concurrency memory cost

因此，基于本次测试结果，可以得出以下判断：

    单张 NVIDIA L40S 不适合完整 BF16 / FP16 加载 Seed-OSS-36B。

如果后续要尝试 Seed-OSS-36B，需要考虑以下路线：

1. 多 GPU tensor parallel
2. 量化加载
3. 降低 max_model_len
4. 先做小上下文 smoke test
5. 使用 vLLM / SGLang 等大模型推理框架
6. 使用更小模型验证服务链路

---

## 9. 与第一周任务的对应关系

第一周任务要求包括：

- 部署 GPU 环境
- 安装 PyTorch、Megatron-LM 等依赖
- 加载 Seed-OSS-36B 模型
- 验证基础推理能力
- 记录并解决模型加载、依赖冲突等环境问题

当前完成情况如下：

| 第一周要求 | 当前状态 |
|---|---|
| 部署 GPU 环境 | 已完成 CX3 GPU smoke test |
| 验证 PyTorch CUDA 环境 | 已完成 |
| 确认 GPU 型号与显存 | 已完成 |
| 基础 GPU 计算测试 | 已完成 |
| Seed-OSS-36B 完整加载 | 未完成 |
| 512K 长上下文验证 | 未完成 |
| Seed-OSS-36B 资源可行性判断 | 已有初步结论 |

当前结论是：

    CX3 单卡 L40S 环境可以支持后续小模型 CUDA 推理实验和 vLLM smoke test，但不适合直接完整运行 BF16 / FP16 的 Seed-OSS-36B。

---

## 10. 下一步计划

基于本次测试结果，后续推荐路线为：

1. 使用当前 CX3 PyTorch + CUDA 环境运行小模型 GPU 推理 smoke test
2. 继续保留本地 FastAPI + TransformersBackend 作为服务链路验证
3. 在第二周正式接入 VLLMBackend
4. 使用 vLLM 在 CX3 上运行小模型 serving smoke test
5. 评估 Seed-OSS-36B 在多 GPU、量化、低 max_model_len 条件下的可行性
6. 将 Seed-OSS-36B 完整加载和 512K 长上下文验证规划到 GPU/vLLM 阶段

---

## 11. 阶段结论

本次 CX3 GPU smoke test 成功验证了项目后续 GPU 推理实验所需的基础环境：

1. 能够通过 PBS 正确申请 GPU 计算节点
2. 能够获得 NVIDIA L40S GPU
3. PyTorch + CUDA module 可用
4. torch.cuda.is_available() 返回 True
5. GPU 张量计算成功

这说明项目已经具备从本地 Apple MPS 小模型验证，进一步迁移到 CX3 NVIDIA GPU 环境的基础条件。

但由于当前单卡 L40S 的显存约为 44.39GB，Seed-OSS-36B 的完整 BF16 / FP16 加载仍然不现实。后续应采用小模型验证服务链路，并将 Seed-OSS-36B 放到多 GPU、量化或 vLLM 可行性实验阶段推进。
