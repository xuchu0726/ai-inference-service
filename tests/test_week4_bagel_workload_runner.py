from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import httpx
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/week4_cloud/run_bagel_workload_manifest.py"

spec = importlib.util.spec_from_file_location(
    "week4_bagel_runner",
    SCRIPT_PATH,
)
assert spec is not None
assert spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def make_case(tmp_path: Path) -> dict:
    image = tmp_path / "sample.png"
    # 最小有效 PNG 头：宽 2，高 3。
    image.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x00\x02"
        b"\x00\x00\x00\x03"
        b"\x08\x02\x00\x00\x00"
    )

    sha256 = hashlib.sha256(image.read_bytes()).hexdigest()
    return {
        "case_id": "case_1",
        "source_case_id": "source_1",
        "scenario": "bagel_test",
        "repeat_index": 1,
        "image_path": str(image),
        "image_sha256": sha256,
        "prompt": "描述图片内容。",
        "show_thinking": False,
        "do_sample": False,
        "temperature": 0.3,
        "max_new_tokens": 64,
    }


def test_prepare_case_reads_dimensions_and_validates_hash(tmp_path: Path) -> None:
    case = make_case(tmp_path)

    prepared = runner.prepare_case(case)

    assert prepared["_image_width"] == 2
    assert prepared["_image_height"] == 3
    assert prepared["_content_type"] == "image/png"
    assert prepared["_image_bytes"]


def test_run_case_records_success_and_protocol(monkeypatch, tmp_path: Path) -> None:
    case = runner.prepare_case(make_case(tmp_path))
    captured = {}

    def fake_post(endpoint, *, files, data, timeout):
        captured["endpoint"] = endpoint
        captured["files"] = files
        captured["data"] = data
        captured["timeout"] = timeout
        request = httpx.Request("POST", endpoint)
        return httpx.Response(
            200,
            request=request,
            json={
                "response": "图片中有测试对象。",
                "latency_seconds": 1.25,
            },
        )

    monkeypatch.setattr(runner.httpx, "post", fake_post)

    record = runner.run_case(
        "http://127.0.0.1:8000/multimodal/generate",
        case,
        timeout_seconds=30.0,
        manifest_index=1,
    )

    assert record["success"] is True
    assert record["http_status"] == 200
    assert record["service_latency_seconds"] == 1.25
    assert record["response_chars"] > 0
    assert captured["endpoint"].endswith("/multimodal/generate")
    assert captured["data"]["prompt"] == "描述图片内容。"
    assert captured["data"]["show_thinking"] == "false"
    assert captured["data"]["max_new_tokens"] == "64"


def test_run_case_records_http_error(monkeypatch, tmp_path: Path) -> None:
    case = runner.prepare_case(make_case(tmp_path))

    def fake_post(endpoint, *, files, data, timeout):
        request = httpx.Request("POST", endpoint)
        return httpx.Response(
            502,
            request=request,
            text="upstream unavailable",
        )

    monkeypatch.setattr(runner.httpx, "post", fake_post)

    record = runner.run_case(
        "http://127.0.0.1:8000/multimodal/generate",
        case,
        timeout_seconds=30.0,
        manifest_index=1,
    )

    assert record["success"] is False
    assert record["http_status"] == 502
    assert record["error_type"] == "http_502"
    assert "upstream unavailable" in record["error"]


def test_summary_reports_p50_p95_and_error_counts() -> None:
    summary = runner.summarize_records(
        [
            {
                "success": True,
                "client_latency_seconds": 1.0,
                "service_latency_seconds": 0.8,
                "source_case_id": "a",
            },
            {
                "success": True,
                "client_latency_seconds": 3.0,
                "service_latency_seconds": 2.5,
                "source_case_id": "a",
            },
            {
                "success": False,
                "client_latency_seconds": 2.0,
                "service_latency_seconds": None,
                "source_case_id": "b",
                "error_type": "http_502",
            },
        ]
    )

    assert summary["runs_requested"] == 3
    assert summary["runs_succeeded"] == 2
    assert summary["success_rate"] == pytest.approx(2 / 3)
    assert summary["client_latency_seconds"]["p50"] == 2.0
    assert summary["error_counts"] == {"http_502": 1}
    assert summary["by_source_case"]["a"]["runs_requested"] == 2
    assert summary["by_source_case"]["b"]["runs_succeeded"] == 0


def test_gpu_summary_tolerates_missing_gpu_samples() -> None:
    summary = runner.gpu_summary(
        [
            {"timestamp_utc": "x", "error": "FileNotFoundError: nvidia-smi"},
        ]
    )

    assert summary["valid_sample_count"] == 0
    assert summary["peak_memory_mib"] is None
    assert summary["sampling_errors"]
