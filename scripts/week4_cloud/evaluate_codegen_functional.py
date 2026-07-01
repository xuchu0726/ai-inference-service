#!/usr/bin/env python3
"""隔离执行 Week4 代码生成任务的功能断言。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path


def extract_code(text: str) -> str:
    match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)
    text = re.sub(r"<seed:think>.*?</seed:think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("<seed:think>", "").replace("</seed:think>", "")
    start = text.find("def ")
    return text[start:].split("```")[0].strip() if start >= 0 else text.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--responses", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--image", default="python:3.11-alpine")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    return parser.parse_args()

def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def classify_failure(stderr: str, stdout: str) -> str:
    text = stderr + "\n" + stdout
    if "SyntaxError" in text:
        return "syntax_error"
    if "ImportError" in text or "ModuleNotFoundError" in text:
        return "import_error"
    if "AssertionError" in text:
        return "test_failed"
    return "runtime_error"


def _tail(value: str | bytes | None, limit: int = 2000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def run_case(
    code: str,
    tests: list[str],
    image: str,
    timeout_seconds: float,
) -> dict:
    if not code:
        return {
            "outcome": "extraction_error",
            "duration_seconds": 0.0,
            "return_code": None,
            "stdout": "",
            "stderr": "",
        }

    with tempfile.TemporaryDirectory(prefix="week4_codegen_") as temp_dir:
        work_dir = Path(temp_dir)
        work_dir.chmod(0o755)
        candidate_path = work_dir / "candidate.py"
        test_path = work_dir / "tests.py"

        candidate_path.write_text(code + "\n", encoding="utf-8")
        test_path.write_text(
            "from candidate import *\n" + "\n".join(tests) + "\n",
            encoding="utf-8",
        )
        candidate_path.chmod(0o644)
        test_path.chmod(0o644)

        container_name = f"week4-codegen-{time.time_ns()}"
        command = [
            "docker", "run", "--rm", "--name", container_name,
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=32m",
            "--memory", "256m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--volume", f"{work_dir.resolve()}:/work:ro",
            "--workdir", "/work",
            image, "python", "tests.py",
        ]

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                capture_output=True,
                text=True,
                check=False,
            )
            return {
                "outcome": "timeout",
                "duration_seconds": round(time.perf_counter() - started, 6),
                "return_code": None,
                "stdout": _tail(exc.stdout),
                "stderr": _tail(exc.stderr),
            }

        duration = round(time.perf_counter() - started, 6)
        stdout = _tail(completed.stdout)
        stderr = _tail(completed.stderr)

        return {
            "outcome": (
                "passed"
                if completed.returncode == 0
                else classify_failure(stderr, stdout)
            ),
            "duration_seconds": duration,
            "return_code": completed.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }


def response_text(record: dict) -> str:
    for key in ("response", "raw_response", "output", "text"):
        value = record.get(key)
        if isinstance(value, str):
            return value

    result = record.get("result")
    if isinstance(result, dict):
        value = result.get("response")
        if isinstance(value, str):
            return value

    raise ValueError("response record has no supported text field")

def main() -> None:
    args = parse_args()
    manifest_rows = load_jsonl(Path(args.manifest))
    response_rows = load_jsonl(Path(args.responses))
    responses = {
        row["case_id"]: row
        for row in response_rows
        if isinstance(row.get("case_id"), str)
    }

    results: list[dict] = []

    for case in manifest_rows:
        case_id = case["case_id"]
        response_record = responses.get(case_id)

        if response_record is None:
            raw_response = ""
            evaluation = {
                "outcome": "missing_response",
                "duration_seconds": 0.0,
                "return_code": None,
                "stdout": "",
                "stderr": "",
            }
        else:
            raw_response = response_text(response_record)
            evaluation = run_case(
                extract_code(raw_response),
                case["tests"],
                args.image,
                args.timeout_seconds,
            )

        results.append({
            "case_id": case_id,
            "function_name": case["function_name"],
            "outcome": evaluation["outcome"],
            "duration_seconds": evaluation["duration_seconds"],
            "return_code": evaluation["return_code"],
            "response_sha256": hashlib.sha256(raw_response.encode("utf-8")).hexdigest(),
            "extracted_code": extract_code(raw_response),
            "stdout": evaluation["stdout"],
            "stderr": evaluation["stderr"],
        })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    outcomes: dict[str, int] = {}
    for row in results:
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1

    summary = {
        "case_count": len(results),
        "passed": outcomes.get("passed", 0),
        "failed": len(results) - outcomes.get("passed", 0),
        "outcomes": outcomes,
    }

    summary_path = output.with_name(output.stem + "_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
