import json
import re
import time
import traceback
import urllib.request
from pathlib import Path
from datetime import datetime

MODEL_NAME = "ByteDance-Seed/Seed-OSS-36B-Instruct"
URL = "http://127.0.0.1:8002/v1/chat/completions"

OUT_DIR = Path("results/week2_hardening")
EVID_DIR = Path("evidence/week2_hardening")
OUT_DIR.mkdir(parents=True, exist_ok=True)
EVID_DIR.mkdir(parents=True, exist_ok=True)

cases = [
    {"id":"codegen_021_reverse_words","prompt":"Write a Python function reverse_words(s) that reverses the order of words separated by whitespace.","function":"reverse_words","tests":["assert reverse_words('hello world') == 'world hello'","assert reverse_words('a b c') == 'c b a'","assert reverse_words('') == ''"]},
    {"id":"codegen_022_anagram","prompt":"Write a Python function are_anagrams(a, b) that returns True if two strings are anagrams, ignoring spaces and case.","function":"are_anagrams","tests":["assert are_anagrams('listen','silent') is True","assert are_anagrams('Dormitory','dirty room') is True","assert are_anagrams('abc','abd') is False"]},
    {"id":"codegen_023_second_largest","prompt":"Write a Python function second_largest(xs) that returns the second largest distinct value, or None if it does not exist.","function":"second_largest","tests":["assert second_largest([1,2,3]) == 2","assert second_largest([3,3,2,1]) == 2","assert second_largest([1,1]) is None"]},
    {"id":"codegen_024_running_sum","prompt":"Write a Python function running_sum(xs) that returns the prefix sums of a list of numbers.","function":"running_sum","tests":["assert running_sum([1,2,3]) == [1,3,6]","assert running_sum([]) == []","assert running_sum([-1,1]) == [-1,0]"]},
    {"id":"codegen_025_matrix_add","prompt":"Write a Python function matrix_add(a, b) that adds two matrices represented as nested lists.","function":"matrix_add","tests":["assert matrix_add([[1,2]], [[3,4]]) == [[4,6]]","assert matrix_add([[1],[2]], [[3],[4]]) == [[4],[6]]"]},
    {"id":"codegen_026_dot_product","prompt":"Write a Python function dot_product(a, b) that returns the dot product of two equal-length lists.","function":"dot_product","tests":["assert dot_product([1,2,3],[4,5,6]) == 32","assert dot_product([],[]) == 0","assert dot_product([1,-1],[1,1]) == 0"]},
    {"id":"codegen_027_remove_none","prompt":"Write a Python function remove_none(xs) that returns a list with all None values removed.","function":"remove_none","tests":["assert remove_none([1,None,2,None]) == [1,2]","assert remove_none([None]) == []","assert remove_none([]) == []"]},
    {"id":"codegen_028_clamp","prompt":"Write a Python function clamp(x, low, high) that clamps x into the inclusive range [low, high].","function":"clamp","tests":["assert clamp(5,1,10) == 5","assert clamp(-1,0,3) == 0","assert clamp(9,0,3) == 3"]},
    {"id":"codegen_029_count_words","prompt":"Write a Python function count_words(text) that returns a dictionary mapping each word to its frequency, splitting on whitespace.","function":"count_words","tests":["assert count_words('a b a') == {'a':2,'b':1}","assert count_words('') == {}"]},
    {"id":"codegen_030_title_case","prompt":"Write a Python function title_case(s) that capitalizes the first character of each word and lowercases the rest.","function":"title_case","tests":["assert title_case('hello WORLD') == 'Hello World'","assert title_case('') == ''"]},
    {"id":"codegen_031_intersection","prompt":"Write a Python function list_intersection(a, b) that returns elements that appear in both lists, preserving the order from a and removing duplicates.","function":"list_intersection","tests":["assert list_intersection([1,2,2,3],[2,3]) == [2,3]","assert list_intersection(['a','b'],['c']) == []"]},
    {"id":"codegen_032_rotate_left","prompt":"Write a Python function rotate_left(xs, k) that rotates a list left by k positions.","function":"rotate_left","tests":["assert rotate_left([1,2,3,4],1) == [2,3,4,1]","assert rotate_left([1,2,3],4) == [2,3,1]","assert rotate_left([],3) == []"]},
    {"id":"codegen_033_is_sorted","prompt":"Write a Python function is_sorted(xs) that returns True if a list is sorted in nondecreasing order.","function":"is_sorted","tests":["assert is_sorted([1,2,2,3]) is True","assert is_sorted([3,2]) is False","assert is_sorted([]) is True"]},
    {"id":"codegen_034_compress_runs","prompt":"Write a Python function compress_runs(xs) that returns a list of (value, count) pairs for consecutive runs.","function":"compress_runs","tests":["assert compress_runs([1,1,2,2,2,1]) == [(1,2),(2,3),(1,1)]","assert compress_runs([]) == []"]},
    {"id":"codegen_035_expand_runs","prompt":"Write a Python function expand_runs(pairs) that expands (value, count) pairs into a flat list.","function":"expand_runs","tests":["assert expand_runs([(1,2),(2,3)]) == [1,1,2,2,2]","assert expand_runs([]) == []"]},
    {"id":"codegen_036_mean","prompt":"Write a Python function mean(xs) that returns the arithmetic mean, or None for an empty list.","function":"mean","tests":["assert mean([1,2,3]) == 2","assert mean([]) is None"]},
    {"id":"codegen_037_median","prompt":"Write a Python function median(xs) that returns the median of a list of numbers, or None for an empty list.","function":"median","tests":["assert median([3,1,2]) == 2","assert median([1,2,3,4]) == 2.5","assert median([]) is None"]},
    {"id":"codegen_038_mode","prompt":"Write a Python function mode(xs) that returns the most frequent element; if there is a tie, return the first one appearing in the input.","function":"mode","tests":["assert mode([1,2,2,3]) == 2","assert mode(['a','b','a','b']) == 'a'","assert mode([]) is None"]},
    {"id":"codegen_039_zip_dict","prompt":"Write a Python function zip_to_dict(keys, values) that returns a dictionary by zipping keys and values.","function":"zip_to_dict","tests":["assert zip_to_dict(['a','b'],[1,2]) == {'a':1,'b':2}","assert zip_to_dict(['a'],[1,2]) == {'a':1}"]},
    {"id":"codegen_040_invert_dict","prompt":"Write a Python function invert_dict(d) that returns a dictionary mapping values to keys. Assume values are unique and hashable.","function":"invert_dict","tests":["assert invert_dict({'a':1,'b':2}) == {1:'a',2:'b'}","assert invert_dict({}) == {}"]},
    {"id":"codegen_041_find_duplicates","prompt":"Write a Python function find_duplicates(xs) that returns a list of values that occur more than once, preserving first duplicate discovery order.","function":"find_duplicates","tests":["assert find_duplicates([1,2,1,3,2,2]) == [1,2]","assert find_duplicates([1,2,3]) == []"]},
    {"id":"codegen_042_strip_punctuation","prompt":"Write a Python function strip_punctuation(s) that removes ASCII punctuation characters from a string.","function":"strip_punctuation","tests":["assert strip_punctuation('Hello, world!') == 'Hello world'","assert strip_punctuation('a.b?c') == 'abc'"]},
    {"id":"codegen_043_word_lengths","prompt":"Write a Python function word_lengths(words) that maps each word to its length.","function":"word_lengths","tests":["assert word_lengths(['hi','world']) == {'hi':2,'world':5}","assert word_lengths([]) == {}"]},
    {"id":"codegen_044_even_numbers","prompt":"Write a Python function even_numbers(xs) that returns only even integers from a list.","function":"even_numbers","tests":["assert even_numbers([1,2,3,4]) == [2,4]","assert even_numbers([]) == []"]},
    {"id":"codegen_045_sum_nested","prompt":"Write a Python function sum_nested(xs) that sums all numbers in a nested list of lists by one level.","function":"sum_nested","tests":["assert sum_nested([[1,2],[3],[]]) == 6","assert sum_nested([]) == 0"]},
    {"id":"codegen_046_min_max","prompt":"Write a Python function min_max(xs) that returns a tuple (min_value, max_value), or None for an empty list.","function":"min_max","tests":["assert min_max([3,1,2]) == (1,3)","assert min_max([]) is None"]},
    {"id":"codegen_047_hamming_distance","prompt":"Write a Python function hamming_distance(a, b) that returns the number of differing positions in two equal-length strings.","function":"hamming_distance","tests":["assert hamming_distance('karolin','kathrin') == 3","assert hamming_distance('', '') == 0"]},
    {"id":"codegen_048_cartesian_product","prompt":"Write a Python function cartesian_product(a, b) that returns a list of pairs for the Cartesian product of two lists.","function":"cartesian_product","tests":["assert cartesian_product([1,2], ['a']) == [(1,'a'),(2,'a')]","assert cartesian_product([], [1]) == []"]},
    {"id":"codegen_049_partition","prompt":"Write a Python function partition(xs, predicate) that returns a tuple (items_true, items_false).","function":"partition","tests":["t, f = partition([1,2,3,4], lambda x: x % 2 == 0); assert t == [2,4] and f == [1,3]"]},
    {"id":"codegen_050_apply_discount","prompt":"Write a Python function apply_discount(price, percent) that returns price after applying a percentage discount.","function":"apply_discount","tests":["assert apply_discount(100, 20) == 80","assert apply_discount(50, 0) == 50"]},
]

def call_model(prompt):
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a strict Python code generator. Return final executable Python code. Avoid explanations."},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 1536,
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"}, method="POST")
    start = time.time()
    with urllib.request.urlopen(req, timeout=240) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return resp.status, time.time() - start, json.loads(raw)

def extract_code(text, function_name):
    fence = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    text = re.sub(r"<seed:think>.*?</seed:think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("<seed:think>", "").replace("</seed:think>", "")
    idx = text.find(f"def {function_name}")
    if idx < 0:
        idx = text.find("def ")
    if idx >= 0:
        text = text[idx:]
    text = text.split("```")[0].strip()
    return text.strip()

def run_tests(code, tests):
    ns = {}
    try:
        exec(code, ns, ns)
        for t in tests:
            exec(t, ns, ns)
        return True, ""
    except Exception:
        return False, traceback.format_exc(limit=6)

results = []
print("===== Seed-OSS additional code generation eval: 30 HumanEval/MBPP-style tasks =====", flush=True)
print("time:", datetime.utcnow().isoformat() + "Z", flush=True)
print("model:", MODEL_NAME, flush=True)

for i, case in enumerate(cases, 1):
    instruction = (
        "Return only one Python code block. "
        f"The code must define exactly the function `{case['function']}` and any required imports. "
        "Do not include tests. Do not include explanations. "
        f"Task: {case['prompt']}"
    )
    print(f"[{i:02d}/{len(cases)}] {case['id']}", flush=True)
    try:
        status, latency, resp = call_model(instruction)
        content = resp["choices"][0]["message"]["content"]
        code = extract_code(content, case["function"])
        passed, error = run_tests(code, case["tests"])
        result = {
            "id": case["id"],
            "function": case["function"],
            "status": status,
            "latency_s": latency,
            "passed": passed,
            "usage": resp.get("usage", {}),
            "raw_output_preview": content[:1000],
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
            "raw_output_preview": "",
            "extracted_code": "",
            "error": repr(e),
        }
    results.append(result)
    print(json.dumps({"id": result["id"], "passed": result["passed"], "latency_s": result["latency_s"], "status": result["status"]}, ensure_ascii=False), flush=True)

passed_count = sum(1 for r in results if r["passed"])
valid_latencies = [r["latency_s"] for r in results if r["latency_s"] is not None]
summary = {
    "created_at": datetime.utcnow().isoformat() + "Z",
    "model": MODEL_NAME,
    "service_profile": "Seed-OSS-36B 512K FP8 KV, 4xA100 TP=4",
    "num_cases": len(results),
    "passed": passed_count,
    "failed": len(results) - passed_count,
    "pass_rate": passed_count / len(results),
    "mean_latency_s": sum(valid_latencies) / max(1, len(valid_latencies)),
    "note": "Additional 30 HumanEval/MBPP-style tasks with local unit tests. Combined with the repaired 20-task run, this provides a 50-task lightweight code generation validation, not a full official benchmark.",
}

detail_path = OUT_DIR / "seed_oss_codegen_eval_additional_30_detail_20260615.json"
summary_path = OUT_DIR / "seed_oss_codegen_eval_additional_30_summary_20260615.json"
detail_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

print("===== Summary =====", flush=True)
print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
