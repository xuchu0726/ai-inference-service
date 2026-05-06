# CX3 vLLM 环境验证记录

## 1. 文档目的

本文档记录本项目在 Imperial CX3 GPU 节点上进行 vLLM 推理环境验证的过程和结果。

本次验证的目的不是直接部署 Seed-OSS-36B，也不是进行正式性能压测，而是确认以下基础条件是否成立：

    1. CX3 GPU 作业是否可以运行在 NVIDIA GPU 计算节点上
    2. Python 3.11 环境是否可用
    3. 是否可以在用户目录下创建独立 Python virtual environment
    4. 是否可以安装 vLLM
    5. vLLM 是否可以正常 import
    6. vLLM 安装后所依赖的 PyTorch CUDA 环境是否可用
    7. PyTorch 是否可以识别 NVIDIA GPU

这一步对应 PTA 第一周和第二周任务中的基础推理环境准备部分，也为后续 vLLM serving、OpenAI-compatible API、多 GPU tensor parallel 和 Seed-OSS-36B 部署实验做前置验证。

---

## 2. 背景说明

本项目最初已经在本地 Apple M4 / MPS 环境下完成了小模型推理服务原型，包括：

    1. FastAPI /generate API
    2. MockBackend / TransformersBackend 后端切换
    3. Qwen2.5-0.5B-Instruct 本地真实推理
    4. benchmark.py 记录 latency、tokens/s、input/output tokens
    5. analyze_benchmark.py 统计 P50 / P95 / error rate

但 PTA 任务要求面向字节 Seed 系列模型，后续涉及：

    1. Seed-OSS-36B
    2. 长上下文推理
    3. Thinking Budget
    4. 高并发推理服务
    5. vLLM / KV Cache / batch 调度
    6. Prometheus / Grafana 监控

这些任务需要 NVIDIA GPU 和更接近真实 serving 场景的推理框架。因此，本阶段在 CX3 上验证 vLLM 环境是否可用。

---

## 3. 作业提交方式

本次验证通过 PBS 作业系统提交到 CX3 GPU 队列，而不是在 login 节点直接运行。

验证作业名称为：

    vllm_env_probe

作业运行方式为：

    qsub deployment/vllm/vllm_env_probe.pbs

作业完成后生成输出文件：

    vllm_env_probe.o2690433

本次作业实际运行在 GPU 计算节点上：

    Host: cx3-20-4

这说明验证过程是在 CX3 计算节点中执行，而不是在 login 节点中执行。

---

## 4. GPU 环境信息

作业中执行 nvidia-smi 后，确认分配到的 GPU 为：

    GPU: NVIDIA L40S
    Driver Version: 580.82.07
    nvidia-smi reported CUDA Version: 13.0
    Visible GPU memory: 46068 MiB

这说明 CX3 当前可以为该项目分配 NVIDIA L40S GPU。L40S 是适合推理实验的高显存 GPU，单卡标称显存为 48GB，PyTorch 可见显存约为 44GB。

---

## 5. Python 与 venv 环境

作业中加载了 CX3 提供的 Python module：

    module purge
    module load tools/prod
    module load Python/3.11.3-GCCcore-12.3.0
    module load CUDA/12.1.1

Python 路径和版本为：

    /sw-eb/software/Python/3.11.3-GCCcore-12.3.0/bin/python
    Python 3.11.3

随后在用户 home 目录下创建并使用 Python virtual environment：

    python -m venv ~/venvs/vllm-cu121
    source ~/venvs/vllm-cu121/bin/activate

该虚拟环境实际路径为：

    /rds/general/user/xc1225/home/venvs/vllm-cu121

该目录位于用户 home/RDS 存储中，因此 PBS 作业结束后仍然保留。

---

## 6. 为什么 venv 不放进 Git 仓库

虽然 vLLM 安装到了用户目录下的 virtual environment，但该 venv 不应提交到 Git 仓库，也不应作为跨平台迁移对象。

原因是 venv 中包含大量与当前机器和系统绑定的内容，例如：

    1. Python 解释器路径
    2. site-packages 中的二进制 wheel
    3. PyTorch / vLLM / xformers / triton / flashinfer 等平台相关依赖
    4. CUDA runtime 相关动态库
    5. 绝对路径引用
    6. Linux ABI / glibc / driver / CUDA 版本相关依赖

因此，即使将该 venv 复制到云平台，也不能保证可用，反而容易造成路径失效、动态库不匹配、CUDA 版本冲突等问题。

本项目应迁移的是：

    1. requirements-vllm.txt
    2. Dockerfile
    3. deployment scripts
    4. README / docs
    5. vLLM 启动命令
    6. benchmark 脚本

而不是迁移 venv 本体。

---

## 7. vLLM 安装过程

在 virtual environment 激活后，作业执行了：

    python -m pip install --upgrade pip setuptools wheel
    python -m pip install vllm

安装过程中，pip 最终安装了：

    vllm==0.11.2

同时，vLLM 自动安装了对应依赖，包括：

    torch==2.9.0+cu128
    transformers==4.57.6
    triton==3.5.0
    xformers==0.0.33.post1
    flashinfer-python==0.5.2
    ray==2.55.1
    fastapi
    uvicorn
    openai
    prometheus_client

其中最关键的是：

    torch: 2.9.0+cu128
    torch cuda: 12.8
    vllm: 0.11.2

这说明该 vLLM 环境使用的是 PyTorch 2.9.0 和 CUDA 12.8 runtime。

---

## 8. vLLM 验证结果

作业中执行以下 Python 检查：

    import torch
    import vllm

    print("torch:", torch.__version__)
    print("torch cuda:", torch.version.cuda)
    print("cuda available:", torch.cuda.is_available())
    print("device count:", torch.cuda.device_count())
    print("device name:", torch.cuda.get_device_name(0))
    print("vllm:", vllm.__version__)

输出结果为：

    torch: 2.9.0+cu128
    torch cuda: 12.8
    cuda available: True
    device count: 1
    device name: NVIDIA L40S
    vllm: 0.11.2

这说明：

    1. vLLM 安装成功
    2. vLLM 可以正常 import
    3. PyTorch CUDA 可用
    4. PyTorch 可以识别 NVIDIA L40S GPU
    5. 当前环境具备后续 vLLM serving smoke test 的基础条件

---

## 9. 与前序 CX3 GPU 验证的关系

在 vLLM 环境验证之前，项目已经完成了 CX3 GPU smoke test，确认：

    1. PBS 可以成功分配 GPU 计算节点
    2. 单卡 NVIDIA L40S 可用
    3. PyTorch/2.1.2-foss-2023a-CUDA-12.1.1 module 可用
    4. torch.cuda.is_available() 返回 True
    5. GPU tensor matmul 测试成功

本次 vLLM 环境验证进一步确认：

    1. CX3 上可以创建独立 Python venv
    2. 可以安装 vLLM
    3. vLLM 自带依赖可以在 CX3 GPU 作业中正常工作
    4. vLLM 使用的 torch 2.9.0+cu128 可以识别 L40S GPU

因此，CX3 已经完成从基础 CUDA/PyTorch 验证到 vLLM 推理框架验证的升级。

---

## 10. 与 2GPU 多卡验证的关系

除单卡环境外，项目还提交了 2GPU probe 作业，确认 CX3 可以分配 2 张 NVIDIA L40S GPU。

2GPU 作业输出显示：

    GPU 0 name: NVIDIA L40S
    GPU 0 total memory GB: 44.39
    GPU 1 name: NVIDIA L40S
    GPU 1 total memory GB: 44.39
    aggregate visible GPU memory GB: 88.78
    GPU 0 matmul OK
    GPU 1 matmul OK

这说明 CX3 支持该项目在单节点内获得 2 张 L40S GPU，并且 PyTorch 可以同时识别两张 GPU。

这为后续 vLLM tensor parallel 提供了基础条件，例如：

    --tensor-parallel-size 2

但 2×L40S 的总可见显存约为 88.78GB，对于 Seed-OSS-36B 仍然偏紧。原因是 36B 模型 BF16/FP16 权重本身约需要 72GB 显存，还需要额外空间容纳 KV Cache、CUDA context、vLLM runtime overhead、通信 buffer 和临时张量。

因此，2GPU 更适合做 vLLM tensor parallel smoke test，不适合作为 Seed-OSS-36B 长上下文或高并发实验的主资源。

---

## 11. 对 Seed-OSS-36B 的影响

Seed-OSS-36B 是 36B 参数规模的大模型。如果使用 BF16 或 FP16 精度，仅模型权重的粗略显存需求为：

    36B parameters × 2 bytes ≈ 72GB

这还不包括：

    1. KV Cache
    2. CUDA context
    3. vLLM runtime overhead
    4. communication buffer
    5. temporary tensors
    6. long-context memory cost
    7. batch / concurrency memory cost

当前已验证的资源包括：

    1. 单卡 L40S，PyTorch 可见显存约 44.39GB
    2. 双卡 L40S，总可见显存约 88.78GB

因此，可以得到以下判断：

    1. 单卡 L40S 不适合完整加载 Seed-OSS-36B
    2. 2×L40S 可以尝试极短上下文 smoke test，但显存余量较小
    3. 若要更稳妥地部署 Seed-OSS-36B，应使用 4×L40S、2×A100 80GB 或更高规格 GPU
    4. 512K 长上下文验证不适合在当前 CX3 单卡或双卡资源上进行
    5. 最终 Seed-OSS-36B 多卡部署和高并发压测更适合迁移到可连续占用 GPU 的云平台完成

---

## 12. 为什么 CX3 验证不是徒劳

CX3 不适合作为长期 API 服务或最终高并发压测平台，但本次验证仍然有明确工程价值。

本次 CX3 阶段已经验证：

    1. GPU 作业提交方式
    2. L40S GPU 可用性
    3. PyTorch CUDA 可用性
    4. vLLM 安装流程
    5. vLLM import 可用性
    6. 单节点 2GPU 可见性
    7. 后续 tensor parallel 的基本条件

这些验证结果可以迁移为：

    1. requirements-vllm.txt
    2. deployment/vllm 脚本
    3. 云平台部署命令
    4. Seed-OSS-36B 资源评估文档
    5. benchmark 实验设计
    6. 简历和面试中的工程证据

因此，CX3 的定位不是最终主战场，而是 proof-of-environment 和 proof-of-serving-pattern。

---

## 13. 云平台迁移策略

由于 CX3 采用 PBS 调度模式，每次使用 GPU 都需要重新排队。作业结束后，GPU 显存、模型进程和 vLLM server 都会释放。

云平台与 CX3 的区别在于：

    1. 云平台可以在租用期间持续占用 GPU
    2. 云平台更适合长时间运行 vLLM server
    3. 云平台更适合 Prometheus / Grafana / 压测 / 演示视频
    4. 云平台更适合 Seed-OSS-36B 多卡部署和最终交付

因此，后续资源路线应为：

    CX3:
        环境验证
        小模型 vLLM smoke test
        脚本调试
        benchmark 流程验证
        文档沉淀

    云平台:
        Seed-OSS-36B vLLM 部署
        tensor parallel
        长时间 API 服务
        benchmark / P50 / P95 / tokens/s
        Prometheus / Grafana
        压测和最终演示

---

## 14. 可迁移资产

本次 CX3 验证后，真正应该保留和迁移的是：

    1. requirements-vllm.txt
    2. deployment/vllm/*.pbs
    3. 后续 Dockerfile
    4. vLLM 启动参数
    5. API 请求脚本
    6. benchmark 脚本
    7. docs/cx3_vllm_env.md
    8. docs/cx3_gpu_smoke_test.md
    9. docs/seed_oss_feasibility.md

不应该迁移的是：

    1. ~/venvs/vllm-cu121 venv 本体
    2. GPU 显存中的模型
    3. 已结束作业中的 vLLM server 进程
    4. 计算节点本地临时状态

云平台上应重新创建 Python 环境，并根据 requirements-vllm.txt 或 Dockerfile 安装依赖。

---

## 15. 阶段结论

本次 CX3 vLLM 环境验证成功。

当前已经确认：

    1. CX3 可以分配 NVIDIA L40S GPU
    2. CX3 可以创建 Python 3.11 venv
    3. vLLM 可以安装成功
    4. vLLM 0.11.2 可以正常 import
    5. vLLM 依赖的 torch 2.9.0+cu128 可以识别 NVIDIA L40S
    6. CX3 可以分配 2×L40S，并且 PyTorch 可以同时识别两张 GPU

因此，本项目已经具备在 CX3 上继续进行小模型 vLLM serving smoke test 的基础条件。

但从最终 PTA 目标看，Seed-OSS-36B、多卡部署、长上下文、高并发压测和监控演示更适合迁移到云 GPU 平台完成。

后续路线应明确为：

    1. CX3 继续完成小模型 vLLM API smoke test
    2. 将环境和命令固化为 requirements、Dockerfile、deployment scripts 和文档
    3. 云 GPU 作为 Seed-OSS-36B 多卡部署和最终压测演示的主平台
