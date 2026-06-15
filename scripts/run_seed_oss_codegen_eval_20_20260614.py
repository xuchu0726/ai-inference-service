import json
import re
import time
import textwrap
import traceback
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

MODEL_NAME = "ByteDance-Seed/Seed-OSS-36B-Instruct"
URL = "http://127.0.0.1:8002/v1/chat/completions"

OUT_DIR = Path("results/week2_hardening")
LOG_DIR = Path("logs/week2_hardening")
EVID_DIR = Path("evidence/week2_hardening")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
EVID_DIR.mkdir(parents=True, exist_ok=True)

cases = [
    {
        "id": "codegen_001_add",
        "prompt": "Write a Python function add(a, b) that returns the sum of two numbers.",
        "function": "add",
        "tests": ["assert add(2, 3) == 5", "assert add(-1, 1) == 0", "assert add(1.5, 2.5) == 4.0"],
    },
    {
        "id": "codegen_002_palindrome",
        "prompt": "Write a Python function is_palindrome(s) that returns True if s is a palindrome, ignoring case.",
        "function": "is_palindrome",
        "tests": ["assert is_palindrome('Racecar') is True", "assert is_palindrome('abc') is False", "assert is_palindrome('') is True"],
    },
    {
        "id": "codegen_003_factorial",
        "prompt": "Write a Python function factorial(n) that returns n factorial for non-negative integers.",
        "function": "factorial",
        "tests": ["assert factorial(0) == 1", "assert factorial(1) == 1", "assert factorial(5) == 120"],
    },
    {
        "id": "codegen_004_fibonacci",
        "prompt": "Write a Python function fibonacci(n) that returns the nth Fibonacci number with fibonacci(0)=0 and fibonacci(1)=1.",
        "function": "fibonacci",
        "tests": ["assert fibonacci(0) == 0", "assert fibonacci(1) == 1", "assert fibonacci(7) == 13"],
    },
    {
        "id": "codegen_005_count_vowels",
        "prompt": "Write a Python function count_vowels(s) that counts vowels in a string.",
        "function": "count_vowels",
        "tests": ["assert count_vowels('hello') == 2", "assert count_vowels('xyz') == 0", "assert count_vowels('AEIOU') == 5"],
    },
    {
        "id": "codegen_006_flatten",
        "prompt": "Write a Python function flatten(xs) that flattens a list of lists by one level.",
        "function": "flatten",
        "tests": ["assert flatten([[1,2],[3],[]]) == [1,2,3]", "assert flatten([]) == []", "assert flatten([['a'], ['b','c']]) == ['a','b','c']"],
    },
    {
        "id": "codegen_007_unique_order",
        "prompt": "Write a Python function unique_preserve_order(xs) that removes duplicates while preserving order.",
        "function": "unique_preserve_order",
        "tests": ["assert unique_preserve_order([1,2,1,3,2]) == [1,2,3]", "assert unique_preserve_order([]) == []", "assert unique_preserve_order(['a','a','b']) == ['a','b']"],
    },
    {
        "id": "codegen_008_binary_search",
        "prompt": "Write a Python function binary_search(xs, target) that returns the index of target in a sorted list, or -1.",
        "function": "binary_search",
        "tests": ["assert binary_search([1,3,5,7], 5) == 2", "assert binary_search([1,3,5,7], 2) == -1", "assert binary_search([], 1) == -1"],
    },
    {
        "id": "codegen_009_merge_sorted",
        "prompt": "Write a Python function merge_sorted(a, b) that merges two sorted lists into one sorted list.",
        "function": "merge_sorted",
        "tests": ["assert merge_sorted([1,3], [2,4]) == [1,2,3,4]", "assert merge_sorted([], [1]) == [1]", "assert merge_sorted([1,1], [1]) == [1,1,1]"],
    },
    {
        "id": "codegen_010_gcd",
        "prompt": "Write a Python function gcd(a, b) that returns the greatest common divisor using Euclid's algorithm.",
        "function": "gcd",
        "tests": ["assert gcd(12, 18) == 6", "assert gcd(7, 5) == 1", "assert gcd(0, 9) == 9"],
    },
    {
        "id": "codegen_011_is_prime",
        "prompt": "Write a Python function is_prime(n) that returns True if n is prime.",
        "function": "is_prime",
        "tests": ["assert is_prime(2) is True", "assert is_prime(17) is True", "assert is_prime(1) is False", "assert is_prime(21) is False"],
    },
    {
        "id": "codegen_012_transpose",
        "prompt": "Write a Python function transpose(matrix) that transposes a rectangular matrix.",
        "function": "transpose",
        "tests": ["assert transpose([[1,2,3],[4,5,6]]) == [[1,4],[2,5],[3,6]]", "assert transpose([[1]]) == [[1]]"],
    },
    {
        "id": "codegen_013_safe_divide",
        "prompt": "Write a Python function safe_divide(a, b, default=None) that returns default when b is zero.",
        "function": "safe_divide",
        "tests": ["assert safe_divide(6, 2) == 3", "assert safe_divide(1, 0) is None", "assert safe_divide(1, 0, default='x') == 'x'"],
    },
    {
        "id": "codegen_014_chunk_list",
        "prompt": "Write a Python function chunk_list(xs, size) that splits a list into chunks of length size.",
        "function": "chunk_list",
        "tests": ["assert chunk_list([1,2,3,4,5], 2) == [[1,2],[3,4],[5]]", "assert chunk_list([], 3) == []"],
    },
    {
        "id": "codegen_015_longest_common_prefix",
        "prompt": "Write a Python function longest_common_prefix(strings) that returns the longest common prefix.",
        "function": "longest_common_prefix",
        "tests": ["assert longest_common_prefix(['flower','flow','flight']) == 'fl'", "assert longest_common_prefix(['dog','racecar']) == ''", "assert longest_common_prefix([]) == ''"],
    },
    {
        "id": "codegen_016_parse_kv",
        "prompt": "Write a Python function parse_key_value_lines(text) that parses lines of the form key=value into a dictionary.",
        "function": "parse_key_value_lines",
        "tests": ["assert parse_key_value_lines('a=1\\nb=2') == {'a':'1','b':'2'}", "assert parse_key_value_lines('x=hello') == {'x':'hello'}"],
    },
    {
        "id": "codegen_017_moving_average",
        "prompt": "Write a Python function moving_average(xs, window) that returns simple moving averages for each full window.",
        "function": "moving_average",
        "tests": ["assert moving_average([1,2,3,4], 2) == [1.5, 2.5, 3.5]", "assert moving_average([1,2], 3) == []"],
    },
    {
        "id": "codegen_018_top_k_frequent",
        "prompt": "Write a Python function top_k_frequent(xs, k) that returns the k most frequent elements. Ties can be in any order.",
        "function": "top_k_frequent",
        "tests": ["assert set(top_k_frequent([1,1,1,2,2,3], 2)) == {1,2}", "assert top_k_frequent([], 2) == []"],
    },
    {
        "id": "codegen_019_group_by_first_letter",
        "prompt": "Write a Python function group_by_first_letter(words) that returns a dict mapping first letters to lists of words.",
        "function": "group_by_first_letter",
        "tests": ["d = group_by_first_letter(['apple','ape','bat']); assert d == {'a':['apple','ape'], 'b':['bat']}"],
    },
    {
        "id": "codegen_020_normalize_vector",
        "prompt": "Write a Python function normalize_vector(xs) that returns a list scaled to unit L2 norm; if norm is zero, return xs unchanged.",
        "function": "normalize_vector",
        "tests": ["out = normalize_vector([3,4]); assert abs(out[0]-0.6) < 1e-9 and abs(out[1]-0.8) < 1e-9", "assert normalize_vector([0,0]) == [0,0]"],
    },
]

def call_model(prompt):
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 384,
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        latency = time.time() - start
        return resp.status, latency, json.loads(raw)

def extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Fall back to first def block.
    idx = text.find("def ")
    if idx >= 0:
        return text[idx:].strip()
    return text.strip()

def run_tests(code, tests):
    ns = {}
    try:
        exec(code, ns, ns)
        for t in tests:
            exec(t, ns, ns)
        return True, ""
    except Exception:
        return False, traceback.format_exc(limit=4)

results = []
print("===== Seed-OSS code generation eval: 20 HumanEval/MBPP-style tasks =====", flush=True)
print("time:", datetime.utcnow().isoformat() + "Z", flush=True)
print("model:", MODEL_NAME, flush=True)

for i, case in enumerate(cases, 1):
    instruction = (
        "Return only one complete Python code block. "
        "Do not include explanations. "
        f"The code must define function `{case['function']}`. "
        f"Task: {case['prompt']}"
    )
    print(f"[{i:02d}/{len(cases)}] {case['id']}", flush=True)
    try:
        status, latency, resp = call_model(instruction)
        content = resp["choices"][0]["message"]["content"]
        code = extract_code(content)
        passed, error = run_tests(code, case["tests"])
        usage = resp.get("usage", {})
        result = {
            "id": case["id"],
            "function": case["function"],
            "status": status,
            "latency_s": latency,
            "passed": passed,
            "usage": usage,
            "output_preview": content[:500],
            "extracted_code": code,
            "error": error,
        }
    except Exception as e:
        result = {
            "id": case["id"],
            "function": case["function"],
            "status": "exception",
            "latency_s": None,
            "passed": False,
            "usage": {},
            "output_preview": "",
            "extracted_code": "",
            "error": repr(e),
        }
    results.append(result)
    print(json.dumps({"id": result["id"], "passed": result["passed"], "latency_s": result["latency_s"], "status": result["status"]}, ensure_ascii=False), flush=True)

passed_count = sum(1 for r in results if r["passed"])
summary = {
    "created_at": datetime.utcnow().isoformat() + "Z",
    "model": MODEL_NAME,
    "service_profile": "Seed-OSS-36B 512K FP8 KV, 4xA100 TP=4",
    "num_cases": len(results),
    "passed": passed_count,
    "failed": len(results) - passed_count,
    "pass_rate": passed_count / len(results),
    "mean_latency_s": sum(r["latency_s"] for r in results if r["latency_s"] is not None) / max(1, sum(1 for r in results if r["latency_s"] is not None)),
    "note": "This is a lightweight HumanEval/MBPP-style validation with local unit tests, not a full official HumanEval or MBPP benchmark.",
}

detail_path = OUT_DIR / "seed_oss_codegen_eval_20_detail_20260614.json"
summary_path = OUT_DIR / "seed_oss_codegen_eval_20_summary_20260614.json"

detail_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print("===== Summary =====", flush=True)
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
