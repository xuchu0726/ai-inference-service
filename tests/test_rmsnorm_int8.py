import pytest
import torch

from app.kernels.rmsnorm_int8 import (
    dequantize_per_row_int8,
    rmsnorm_int8_fused,
    rmsnorm_int8_reference,
    triton_is_available,
)


@pytest.mark.parametrize("dtype", [torch.float32, torch.float16])
@pytest.mark.parametrize("shape", [(1, 17), (4, 128), (8, 1024)])
def test_reference_returns_expected_shapes_and_dtypes(dtype, shape):
    torch.manual_seed(7)

    x = torch.randn(*shape, dtype=dtype)
    weight = torch.randn(shape[1], dtype=dtype)

    quantized, scales = rmsnorm_int8_reference(x, weight)

    assert quantized.shape == x.shape
    assert quantized.dtype == torch.int8
    assert scales.shape == (shape[0],)
    assert scales.dtype == torch.float32
    assert torch.all(scales > 0)


def test_reference_dequantization_error_is_bounded():
    torch.manual_seed(11)

    x = torch.randn(8, 256, dtype=torch.float32)
    weight = torch.randn(256, dtype=torch.float32)

    quantized, scales = rmsnorm_int8_reference(x, weight)
    restored = dequantize_per_row_int8(quantized, scales)

    reference_fp32 = (
        x
        * torch.rsqrt(x.square().mean(dim=1, keepdim=True) + 1.0e-6)
        * weight
    )

    max_scale = scales.max().item()
    max_error = (restored - reference_fp32).abs().max().item()

    assert max_error <= max_scale / 2 + 1.0e-6


def test_reference_rejects_mismatched_hidden_dimension():
    with pytest.raises(ValueError, match="must match"):
        rmsnorm_int8_reference(
            torch.randn(2, 16),
            torch.randn(15),
        )


@pytest.mark.skipif(
    not triton_is_available(),
    reason="requires CUDA and Triton runtime",
)
@pytest.mark.parametrize("dtype", [torch.float16, torch.bfloat16])
@pytest.mark.parametrize("shape", [(1, 1024), (8, 4096), (32, 8192)])
def test_fused_matches_reference(dtype, shape):
    torch.manual_seed(17)

    x = torch.randn(*shape, device="cuda", dtype=dtype)
    weight = torch.randn(shape[1], device="cuda", dtype=dtype)

    expected_q, expected_scales = rmsnorm_int8_reference(x, weight)
    actual_q, actual_scales = rmsnorm_int8_fused(x, weight)

    torch.testing.assert_close(
        actual_scales,
        expected_scales,
        rtol=2e-4,
        atol=2e-5,
    )

    assert torch.equal(actual_q, expected_q)
