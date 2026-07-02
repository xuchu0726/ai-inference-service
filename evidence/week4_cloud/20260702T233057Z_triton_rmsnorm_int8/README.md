# Triton RMSNorm-INT8 融合微内核验证

## 实验对象
- A100-SXM4-80GB
- PyTorch 2.9.0+cu128
- CUDA 12.8
- Triton fused RMSNorm + per-row INT8 quantization
- 对照：PyTorch unfused reference

## 验证内容
- 覆盖 FP16/BF16 与 1024/4096/8192 hidden size。
- 先比较 INT8 输出是否完全一致，再比较 per-row scale 与反量化误差。
- 每个 case warmup 20 次、正式测量 100 次。

## 结果边界
- 结果仅表示独立微内核相对当前 PyTorch reference 的性能。
- 该内核尚未接入 vLLM runtime，因此不将其速度提升外推为端到端模型吞吐提升。
