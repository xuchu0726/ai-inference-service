import pytest

import app.inference as inference_module
from app.backends.vllm_backend import VLLMBackend


def _configure_vllm(monkeypatch, primary_url, fallback_url):
    monkeypatch.setattr(inference_module, "INFERENCE_BACKEND", "vllm")
    monkeypatch.setattr(inference_module, "VLLM_BASE_URL", primary_url)
    monkeypatch.setattr(
        inference_module,
        "VLLM_FALLBACK_BASE_URL",
        fallback_url,
    )
    monkeypatch.setattr(
        inference_module,
        "VLLM_MODEL_NAME",
        "ByteDance-Seed/Seed-OSS-36B-Instruct",
    )
    monkeypatch.setattr(
        inference_module,
        "VLLM_FALLBACK_MODEL_NAME",
        "ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8",
    )
    monkeypatch.setattr(
        inference_module,
        "VLLM_TIMEOUT_SECONDS",
        30,
    )
    monkeypatch.setattr(
        inference_module,
        "VLLM_FALLBACK_TIMEOUT_SECONDS",
        30,
    )
    monkeypatch.setattr(
        inference_module,
        "VLLM_ENABLE_SEED_THINKING_BUDGET",
        True,
    )


def test_fallback_backend_uses_independent_vllm_endpoint(monkeypatch):
    _configure_vllm(
        monkeypatch,
        primary_url="http://primary-vllm:8000/v1",
        fallback_url="http://fallback-vllm:8000/v1",
    )

    fallback = inference_module._build_fallback_backend()

    assert isinstance(fallback, VLLMBackend)
    assert fallback.base_url == "http://fallback-vllm:8000/v1"
    assert fallback.model_name == "ByteDance-Seed/Seed-OSS-36B-Instruct-W8A8"
    assert fallback.timeout_seconds == 30
    assert fallback.enable_seed_thinking_budget is True


def test_fallback_backend_rejects_primary_endpoint_reuse(monkeypatch):
    _configure_vllm(
        monkeypatch,
        primary_url="http://shared-vllm:8000/v1",
        fallback_url="http://shared-vllm:8000/v1",
    )

    with pytest.raises(
        ValueError,
        match="VLLM_FALLBACK_BASE_URL must be different",
    ):
        inference_module._build_fallback_backend()
