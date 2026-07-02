"""RMSNorm 后按行 INT8 量化的独立 Triton 微内核。

边界：
- 输入为 contiguous 的二维 CUDA Tensor，[M, H]。
- 输出为 int8 quantized tensor 与每行 float32 scale。
- 该模块未接入 vLLM runtime；仅用于独立正确性与性能实验。
"""

from __future__ import annotations

from typing import Final

import torch

try:
    import triton
    import triton.language as tl
except ImportError:
    triton = None
    tl = None


MAX_FUSED_HIDDEN_SIZE: Final[int] = 8192
MIN_SCALE: Final[float] = 1.0e-8


def triton_is_available() -> bool:
    """返回当前环境是否同时具备 Triton 与 CUDA。"""
    return triton is not None and torch.cuda.is_available()


def _validate_inputs(x: torch.Tensor, weight: torch.Tensor, eps: float) -> None:
    if x.ndim != 2:
        raise ValueError(f"x must have shape [M, H], got {tuple(x.shape)}")

    if weight.ndim != 1:
        raise ValueError(
            f"weight must have shape [H], got {tuple(weight.shape)}"
        )

    if x.shape[1] != weight.shape[0]:
        raise ValueError(
            "x hidden dimension and weight length must match: "
            f"{x.shape[1]} != {weight.shape[0]}"
        )

    if x.dtype not in {torch.float16, torch.bfloat16, torch.float32}:
        raise TypeError(f"unsupported x dtype: {x.dtype}")

    if weight.dtype not in {
        torch.float16,
        torch.bfloat16,
        torch.float32,
    }:
        raise TypeError(f"unsupported weight dtype: {weight.dtype}")

    if eps <= 0:
        raise ValueError("eps must be positive")


def _round_half_away_from_zero(values: torch.Tensor) -> torch.Tensor:
    """定义 reference 与 Triton kernel 共享的确定性舍入规则。"""
    return torch.where(
        values >= 0,
        torch.floor(values + 0.5),
        torch.ceil(values - 0.5),
    )


def rmsnorm_int8_reference(
    x: torch.Tensor,
    weight: torch.Tensor,
    *,
    eps: float = 1.0e-6,
) -> tuple[torch.Tensor, torch.Tensor]:
    """PyTorch unfused reference。

    返回：
    - quantized: int8，[M, H]
    - scales: float32，[M]，每行对称量化 scale
    """
    _validate_inputs(x, weight, eps)

    x_fp32 = x.float()
    weight_fp32 = weight.float()

    inverse_rms = torch.rsqrt(
        x_fp32.square().mean(dim=1, keepdim=True) + eps
    )
    normalized = x_fp32 * inverse_rms * weight_fp32

    scales = (
        normalized.abs().amax(dim=1).clamp_min(MIN_SCALE) / 127.0
    )
    quantized = _round_half_away_from_zero(
        normalized / scales.unsqueeze(1)
    )
    quantized = quantized.clamp(-127, 127).to(torch.int8)

    return quantized, scales


if triton is not None:

    @triton.jit
    def _rmsnorm_int8_kernel(
        x_ptr,
        weight_ptr,
        quantized_ptr,
        scale_ptr,
        stride_m,
        hidden_size: tl.constexpr,
        eps: tl.constexpr,
        block_size: tl.constexpr,
    ):
        row = tl.program_id(axis=0)
        offsets = tl.arange(0, block_size)
        mask = offsets < hidden_size

        x = tl.load(
            x_ptr + row * stride_m + offsets,
            mask=mask,
            other=0.0,
        ).to(tl.float32)

        weight = tl.load(
            weight_ptr + offsets,
            mask=mask,
            other=0.0,
        ).to(tl.float32)

        sum_squares = tl.sum(x * x, axis=0)
        inverse_rms = tl.rsqrt(sum_squares / hidden_size + eps)

        normalized = x * inverse_rms * weight
        scale = tl.maximum(
            tl.max(tl.abs(normalized), axis=0) / 127.0,
            1.0e-8,
        )

        scaled = normalized / scale
        rounded = tl.where(
            scaled >= 0.0,
            tl.floor(scaled + 0.5),
            tl.ceil(scaled - 0.5),
        )
        clipped = tl.maximum(tl.minimum(rounded, 127.0), -127.0)

        tl.store(
            quantized_ptr + row * stride_m + offsets,
            clipped.to(tl.int8),
            mask=mask,
        )
        tl.store(scale_ptr + row, scale)

else:
    _rmsnorm_int8_kernel = None


def rmsnorm_int8_fused(
    x: torch.Tensor,
    weight: torch.Tensor,
    *,
    eps: float = 1.0e-6,
) -> tuple[torch.Tensor, torch.Tensor]:
    """执行 Triton fused RMSNorm + per-row INT8 quantization。

    仅支持 CUDA，且第一版仅覆盖 H <= MAX_FUSED_HIDDEN_SIZE。
    """
    _validate_inputs(x, weight, eps)

    if not triton_is_available():
        raise RuntimeError(
            "Triton CUDA runtime is unavailable. "
            "Use rmsnorm_int8_reference for CPU/local validation."
        )

    if not x.is_cuda or not weight.is_cuda:
        raise ValueError("fused kernel requires CUDA x and weight tensors")

    if x.device != weight.device:
        raise ValueError("x and weight must be on the same CUDA device")

    if not x.is_contiguous() or not weight.is_contiguous():
        raise ValueError("fused kernel requires contiguous x and weight")

    rows, hidden_size = x.shape

    if hidden_size > MAX_FUSED_HIDDEN_SIZE:
        raise ValueError(
            f"hidden_size={hidden_size} exceeds "
            f"MAX_FUSED_HIDDEN_SIZE={MAX_FUSED_HIDDEN_SIZE}"
        )

    block_size = triton.next_power_of_2(hidden_size)
    quantized = torch.empty_like(x, dtype=torch.int8)
    scales = torch.empty(rows, device=x.device, dtype=torch.float32)

    num_warps = 4 if block_size <= 4096 else 8

    _rmsnorm_int8_kernel[(rows,)](
        x,
        weight,
        quantized,
        scales,
        x.stride(0),
        hidden_size=hidden_size,
        eps=eps,
        block_size=block_size,
        num_warps=num_warps,
    )

    return quantized, scales


def dequantize_per_row_int8(
    quantized: torch.Tensor,
    scales: torch.Tensor,
) -> torch.Tensor:
    """用于误差分析的反量化辅助函数。"""
    if quantized.ndim != 2:
        raise ValueError("quantized must have shape [M, H]")

    if scales.ndim != 1 or scales.shape[0] != quantized.shape[0]:
        raise ValueError("scales must have shape [M]")

    return quantized.float() * scales.float().unsqueeze(1)
