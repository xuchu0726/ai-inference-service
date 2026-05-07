import argparse
import csv
import random
import statistics
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class Request:
    request_id: int
    arrival_time: float
    prompt_tokens: int
    output_tokens: int


@dataclass
class Result:
    policy: str
    request_id: int
    arrival_time: float
    prompt_tokens: int
    output_tokens: int
    start_time: float
    finish_time: float
    wait_time: float
    latency: float


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * p
    lower = int(index)
    upper = min(lower + 1, len(sorted_values) - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def generate_requests(
    num_requests: int,
    seed: int,
    avg_interarrival: float,
    min_prompt_tokens: int,
    max_prompt_tokens: int,
    min_output_tokens: int,
    max_output_tokens: int,
) -> list[Request]:
    random.seed(seed)
    requests: list[Request] = []
    current_time = 0.0

    for request_id in range(1, num_requests + 1):
        current_time += random.expovariate(1.0 / avg_interarrival)

        prompt_tokens = random.randint(min_prompt_tokens, max_prompt_tokens)
        output_tokens = random.randint(min_output_tokens, max_output_tokens)

        requests.append(
            Request(
                request_id=request_id,
                arrival_time=round(current_time, 4),
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
            )
        )

    return requests


def simulate_static_batching(
    requests: list[Request],
    batch_size: int,
    prefill_time_per_token: float,
    decode_time_per_token_per_batch: float,
) -> tuple[list[Result], dict[str, float]]:
    """
    Static batching model:
    - Requests are processed in fixed batches.
    - A batch starts when the GPU is free and at least one request has arrived.
    - The batch runs until the longest request in that batch finishes.
    - Shorter requests in the same batch still wait for the batch to complete.

    This intentionally models the inefficiency of rigid batching.
    """
    results: list[Result] = []
    sorted_requests = sorted(requests, key=lambda r: r.arrival_time)

    index = 0
    current_time = 0.0
    gpu_busy_time = 0.0
    gpu_idle_time = 0.0

    while index < len(sorted_requests):
        if current_time < sorted_requests[index].arrival_time:
            idle_gap = sorted_requests[index].arrival_time - current_time
            gpu_idle_time += idle_gap
            current_time = sorted_requests[index].arrival_time

        available: list[Request] = []
        while (
            index < len(sorted_requests)
            and sorted_requests[index].arrival_time <= current_time
            and len(available) < batch_size
        ):
            available.append(sorted_requests[index])
            index += 1

        while index < len(sorted_requests) and len(available) < batch_size:
            # Static batching waits to form a larger batch if future requests exist.
            next_request = sorted_requests[index]
            if current_time < next_request.arrival_time:
                idle_gap = next_request.arrival_time - current_time
                gpu_idle_time += idle_gap
                current_time = next_request.arrival_time
            available.append(next_request)
            index += 1

        batch_start = current_time

        max_prompt_tokens = max(r.prompt_tokens for r in available)
        max_output_tokens = max(r.output_tokens for r in available)

        prefill_time = max_prompt_tokens * prefill_time_per_token
        decode_time = max_output_tokens * decode_time_per_token_per_batch * len(available)
        batch_duration = prefill_time + decode_time
        batch_finish = batch_start + batch_duration

        gpu_busy_time += batch_duration

        for request in available:
            results.append(
                Result(
                    policy="static_batching",
                    request_id=request.request_id,
                    arrival_time=request.arrival_time,
                    prompt_tokens=request.prompt_tokens,
                    output_tokens=request.output_tokens,
                    start_time=round(batch_start, 6),
                    finish_time=round(batch_finish, 6),
                    wait_time=round(batch_start - request.arrival_time, 6),
                    latency=round(batch_finish - request.arrival_time, 6),
                )
            )

        current_time = batch_finish

    metrics = summarize_policy(
        policy="static_batching",
        results=results,
        gpu_busy_time=gpu_busy_time,
        gpu_idle_time=gpu_idle_time,
    )
    return results, metrics


def simulate_continuous_batching(
    requests: list[Request],
    max_active_requests: int,
    prefill_time_per_token: float,
    decode_step_time_base: float,
    decode_step_time_per_request: float,
) -> tuple[list[Result], dict[str, float]]:
    """
    Continuous batching model:
    - Requests arrive over time.
    - GPU keeps a dynamic active set.
    - Finished requests leave immediately.
    - New waiting requests fill empty slots.
    - Decode proceeds token-by-token.

    This is a simplified model of the online serving behavior that frameworks
    such as vLLM are designed to support.
    """
    sorted_requests = sorted(requests, key=lambda r: r.arrival_time)
    pending_index = 0
    waiting: list[Request] = []
    active: list[dict] = []
    completed: list[Result] = []

    current_time = 0.0
    gpu_busy_time = 0.0
    gpu_idle_time = 0.0

    start_times: dict[int, float] = {}

    while len(completed) < len(sorted_requests):
        while (
            pending_index < len(sorted_requests)
            and sorted_requests[pending_index].arrival_time <= current_time
        ):
            waiting.append(sorted_requests[pending_index])
            pending_index += 1

        while waiting and len(active) < max_active_requests:
            request = waiting.pop(0)
            start_times[request.request_id] = current_time

            prefill_time = request.prompt_tokens * prefill_time_per_token
            current_time += prefill_time
            gpu_busy_time += prefill_time

            while (
                pending_index < len(sorted_requests)
                and sorted_requests[pending_index].arrival_time <= current_time
            ):
                waiting.append(sorted_requests[pending_index])
                pending_index += 1

            active.append(
                {
                    "request": request,
                    "remaining_output_tokens": request.output_tokens,
                }
            )

        if not active:
            if pending_index < len(sorted_requests):
                next_arrival = sorted_requests[pending_index].arrival_time
                if current_time < next_arrival:
                    gpu_idle_time += next_arrival - current_time
                    current_time = next_arrival
                continue
            break

        # One decode step for all active requests.
        step_time = decode_step_time_base + decode_step_time_per_request * len(active)
        current_time += step_time
        gpu_busy_time += step_time

        still_active: list[dict] = []
        for item in active:
            item["remaining_output_tokens"] -= 1
            request = item["request"]

            if item["remaining_output_tokens"] <= 0:
                start_time = start_times[request.request_id]
                completed.append(
                    Result(
                        policy="continuous_batching",
                        request_id=request.request_id,
                        arrival_time=request.arrival_time,
                        prompt_tokens=request.prompt_tokens,
                        output_tokens=request.output_tokens,
                        start_time=round(start_time, 6),
                        finish_time=round(current_time, 6),
                        wait_time=round(start_time - request.arrival_time, 6),
                        latency=round(current_time - request.arrival_time, 6),
                    )
                )
            else:
                still_active.append(item)

        active = still_active

    metrics = summarize_policy(
        policy="continuous_batching",
        results=completed,
        gpu_busy_time=gpu_busy_time,
        gpu_idle_time=gpu_idle_time,
    )
    return completed, metrics


def summarize_policy(
    policy: str,
    results: list[Result],
    gpu_busy_time: float,
    gpu_idle_time: float,
) -> dict[str, float]:
    latencies = [r.latency for r in results]
    wait_times = [r.wait_time for r in results]
    finish_time = max((r.finish_time for r in results), default=0.0)
    total_output_tokens = sum(r.output_tokens for r in results)

    total_time = gpu_busy_time + gpu_idle_time
    gpu_utilization = gpu_busy_time / total_time if total_time > 0 else 0.0
    throughput = total_output_tokens / finish_time if finish_time > 0 else 0.0

    return {
        "policy": policy,
        "num_requests": len(results),
        "avg_wait_time": round(statistics.mean(wait_times), 6) if wait_times else 0.0,
        "p50_wait_time": round(percentile(wait_times, 0.50), 6),
        "p95_wait_time": round(percentile(wait_times, 0.95), 6),
        "avg_latency": round(statistics.mean(latencies), 6) if latencies else 0.0,
        "p50_latency": round(percentile(latencies, 0.50), 6),
        "p95_latency": round(percentile(latencies, 0.95), 6),
        "finish_time": round(finish_time, 6),
        "gpu_busy_time": round(gpu_busy_time, 6),
        "gpu_idle_time": round(gpu_idle_time, 6),
        "gpu_utilization": round(gpu_utilization, 6),
        "output_tokens_per_time": round(throughput, 6),
    }


def write_request_csv(path: Path, requests: list[Request]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "request_id",
                "arrival_time",
                "prompt_tokens",
                "output_tokens",
            ],
        )
        writer.writeheader()
        for request in requests:
            writer.writerow(asdict(request))


def write_result_csv(path: Path, results: list[Result]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "policy",
                "request_id",
                "arrival_time",
                "prompt_tokens",
                "output_tokens",
                "start_time",
                "finish_time",
                "wait_time",
                "latency",
            ],
        )
        writer.writeheader()
        for result in sorted(results, key=lambda x: (x.policy, x.request_id)):
            writer.writerow(asdict(result))


def write_summary_csv(path: Path, summaries: list[dict[str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(summaries[0].keys())

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulate static batching vs continuous batching for LLM serving."
    )
    parser.add_argument("--num-requests", type=int, default=64)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--avg-interarrival", type=float, default=0.08)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--min-prompt-tokens", type=int, default=32)
    parser.add_argument("--max-prompt-tokens", type=int, default=1024)
    parser.add_argument("--min-output-tokens", type=int, default=16)
    parser.add_argument("--max-output-tokens", type=int, default=256)
    parser.add_argument("--prefill-time-per-token", type=float, default=0.0004)
    parser.add_argument("--static-decode-time-per-token-per-batch", type=float, default=0.0012)
    parser.add_argument("--continuous-decode-step-time-base", type=float, default=0.001)
    parser.add_argument("--continuous-decode-step-time-per-request", type=float, default=0.00018)
    parser.add_argument("--request-output", default="results/scheduler_requests.csv")
    parser.add_argument("--result-output", default="results/scheduler_simulation.csv")
    parser.add_argument("--summary-output", default="results/scheduler_simulation_summary.csv")

    args = parser.parse_args()

    requests = generate_requests(
        num_requests=args.num_requests,
        seed=args.seed,
        avg_interarrival=args.avg_interarrival,
        min_prompt_tokens=args.min_prompt_tokens,
        max_prompt_tokens=args.max_prompt_tokens,
        min_output_tokens=args.min_output_tokens,
        max_output_tokens=args.max_output_tokens,
    )

    static_results, static_summary = simulate_static_batching(
        requests=requests,
        batch_size=args.batch_size,
        prefill_time_per_token=args.prefill_time_per_token,
        decode_time_per_token_per_batch=args.static_decode_time_per_token_per_batch,
    )

    continuous_results, continuous_summary = simulate_continuous_batching(
        requests=requests,
        max_active_requests=args.batch_size,
        prefill_time_per_token=args.prefill_time_per_token,
        decode_step_time_base=args.continuous_decode_step_time_base,
        decode_step_time_per_request=args.continuous_decode_step_time_per_request,
    )

    all_results = static_results + continuous_results
    summaries = [static_summary, continuous_summary]

    write_request_csv(Path(args.request_output), requests)
    write_result_csv(Path(args.result_output), all_results)
    write_summary_csv(Path(args.summary_output), summaries)

    print("===== SCHEDULER SIMULATION SUMMARY =====")
    for summary in summaries:
        print()
        print(f"policy: {summary['policy']}")
        for key, value in summary.items():
            if key != "policy":
                print(f"{key}: {value}")

    print()
    print(f"saved_requests_csv: {args.request_output}")
    print(f"saved_results_csv: {args.result_output}")
    print(f"saved_summary_csv: {args.summary_output}")


if __name__ == "__main__":
    main()
