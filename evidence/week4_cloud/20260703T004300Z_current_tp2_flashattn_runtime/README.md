# 当前 4×A100 主备 TP=2 FlashAttention 运行证据

## 结论
当前运行中的 Seed-OSS-36B W8A8 vLLM 主备服务均由 vLLM backend selector 选择 `FLASH_ATTN`。

## 进程映射
- fallback：PID 1948，stdout/stderr 指向 `week4_fallback_tp2_8010.log`。
- recovered primary：PID 4368，stdout/stderr 指向 `week4_primary_tp2_8002_recovered.log`。

## 范围
这是 vLLM 自动选择并实际启用的 attention backend。
不表示手写或改造了 FlashAttention 算子，也没有单独进行 backend 对比实验。
