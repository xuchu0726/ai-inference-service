from app.routing import (
    WorkloadType,
    classify_workload,
    select_serving_profile,
)


def test_short_output_burst_profile_for_high_concurrency_short_output():
    workload = classify_workload(
        prompt_chars=500,
        max_new_tokens=128,
        concurrency_hint=8,
    )
    profile = select_serving_profile(
        prompt_chars=500,
        max_new_tokens=128,
        concurrency_hint=8,
    )

    assert workload == WorkloadType.SHORT_OUTPUT_BURST
    assert profile.name == "short_output_burst_32768"
    assert profile.max_num_batched_tokens == 32768


def test_long_output_profile_for_large_generation_budget():
    workload = classify_workload(
        prompt_chars=500,
        max_new_tokens=512,
        concurrency_hint=4,
    )
    profile = select_serving_profile(
        prompt_chars=500,
        max_new_tokens=512,
        concurrency_hint=4,
    )

    assert workload == WorkloadType.LONG_OUTPUT_OR_MIXED
    assert profile.name == "long_output_or_mixed_8192"
    assert profile.max_num_batched_tokens == 8192


def test_long_context_profile_for_large_prompt():
    workload = classify_workload(
        prompt_chars=12000,
        max_new_tokens=128,
        concurrency_hint=4,
    )
    profile = select_serving_profile(
        prompt_chars=12000,
        max_new_tokens=128,
        concurrency_hint=4,
    )

    assert workload == WorkloadType.LONG_OUTPUT_OR_MIXED
    assert profile.max_num_batched_tokens == 8192
