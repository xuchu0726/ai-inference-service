import csv
from pathlib import Path
from statistics import mean

INPUT_PATH = Path("results/thinking_budget_benchmark.csv")
OUTPUT_PATH = Path("results/benchmark_summary.csv")


def percentile(values, p):
    if not values:
        return None

    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (p / 100)
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)

    if lower == upper:
        return sorted_values[lower]

    weight = k - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


rows = []

with INPUT_PATH.open("r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

client_latencies = [
    to_float(row.get("client_latency_seconds"))
    for row in rows
    if to_float(row.get("client_latency_seconds")) is not None
]

server_latencies = [
    to_float(row.get("server_latency_seconds"))
    for row in rows
    if to_float(row.get("server_latency_seconds")) is not None
]

tokens_per_second_values = [
    to_float(row.get("tokens_per_second"))
    for row in rows
    if to_float(row.get("tokens_per_second")) is not None
]

status_codes = [row.get("status_code") for row in rows]

total_requests = len(rows)
successful_requests = sum(1 for code in status_codes if code == "200")
failed_requests = total_requests - successful_requests
error_rate = failed_requests / total_requests if total_requests > 0 else 0

summary = {
    "total_requests": total_requests,
    "successful_requests": successful_requests,
    "failed_requests": failed_requests,
    "error_rate": round(error_rate, 6),

    "client_latency_avg": round(mean(client_latencies), 6),
    "client_latency_p50": round(percentile(client_latencies, 50), 6),
    "client_latency_p95": round(percentile(client_latencies, 95), 6),

    "server_latency_avg": round(mean(server_latencies), 6),
    "server_latency_p50": round(percentile(server_latencies, 50), 6),
    "server_latency_p95": round(percentile(server_latencies, 95), 6),

    "tokens_per_second_avg": round(mean(tokens_per_second_values), 6),
    "tokens_per_second_p50": round(percentile(tokens_per_second_values, 50), 6),
    "tokens_per_second_p95": round(percentile(tokens_per_second_values, 95), 6),
}

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(summary.keys()))
    writer.writeheader()
    writer.writerow(summary)

print("Benchmark summary:")
for key, value in summary.items():
    print(f"{key}: {value}")

print(f"\nSummary saved to: {OUTPUT_PATH}")