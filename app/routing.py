from dataclasses import dataclass
from enum import Enum


class WorkloadType(str, Enum):
    SHORT_OUTPUT_BURST = "short_output_burst"
    LONG_OUTPUT_OR_MIXED = "long_output_or_mixed"


@dataclass(frozen=True)
class ServingProfile:
    name: str
    max_num_batched_tokens: int
    reason: str


SHORT_OUTPUT_BURST_PROFILE = ServingProfile(
    name="short_output_burst_32768",
    max_num_batched_tokens=32768,
    reason=(
        "Short-output burst workload favors a larger batch-token budget. "
        "Week2 measurements showed QPS improving from 1.921 to 2.371 and "
        "P95 latency decreasing from 7.350s to 3.415s under c8 burst."
    ),
)

LONG_OUTPUT_OR_MIXED_PROFILE = ServingProfile(
    name="long_output_or_mixed_8192",
    max_num_batched_tokens=8192,
    reason=(
        "Long-output or mixed workload favors a more conservative batch-token "
        "budget. Week2 measurements showed lower P95 latency with 8192 "
        "than 32768 under long-output c4."
    ),
)


def classify_workload(
    prompt_chars: int,
    max_new_tokens: int,
    concurrency_hint: int | None = None,
) -> WorkloadType:
    if max_new_tokens >= 384:
        return WorkloadType.LONG_OUTPUT_OR_MIXED

    if prompt_chars >= 8000:
        return WorkloadType.LONG_OUTPUT_OR_MIXED

    if concurrency_hint is not None and concurrency_hint >= 8 and max_new_tokens <= 160:
        return WorkloadType.SHORT_OUTPUT_BURST

    if max_new_tokens <= 160:
        return WorkloadType.SHORT_OUTPUT_BURST

    return WorkloadType.LONG_OUTPUT_OR_MIXED


def select_serving_profile(
    prompt_chars: int,
    max_new_tokens: int,
    concurrency_hint: int | None = None,
) -> ServingProfile:
    workload = classify_workload(
        prompt_chars=prompt_chars,
        max_new_tokens=max_new_tokens,
        concurrency_hint=concurrency_hint,
    )

    if workload == WorkloadType.SHORT_OUTPUT_BURST:
        return SHORT_OUTPUT_BURST_PROFILE

    return LONG_OUTPUT_OR_MIXED_PROFILE
