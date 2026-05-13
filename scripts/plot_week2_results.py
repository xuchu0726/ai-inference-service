import argparse
import csv
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    value = str(value).strip()
    if value == "" or value.lower() == "none":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def plot_line(
    x: list[float],
    y: list[float],
    xlabel: str,
    ylabel: str,
    title: str,
    output: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)

    plt.figure()
    plt.plot(x, y, marker="o")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output, dpi=200)
    plt.close()


def load_concurrency_summaries(results_dir: Path) -> list[dict[str, Any]]:
    rows = []

    for path in sorted(results_dir.glob("week2_concurrency_c*_summary.csv")):
        data = read_csv(path)
        if not data:
            continue

        row = data[0]
        concurrency_values = row.get("concurrency_values", "")
        first_concurrency = concurrency_values.split("|")[0] if concurrency_values else ""

        rows.append(
            {
                "file": str(path),
                "concurrency": to_float(first_concurrency),
                "throughput_qps": to_float(row.get("throughput_qps")),
                "client_latency_p50": to_float(row.get("client_latency_seconds_p50")),
                "client_latency_p95": to_float(row.get("client_latency_seconds_p95")),
                "tokens_per_second_avg": to_float(row.get("tokens_per_second_avg")),
                "error_rate": to_float(row.get("error_rate")),
            }
        )

    rows = [r for r in rows if r["concurrency"] is not None]
    rows.sort(key=lambda r: r["concurrency"])
    return rows


def plot_concurrency(results_dir: Path, figures_dir: Path) -> None:
    rows = load_concurrency_summaries(results_dir)

    if not rows:
        print("No week2_concurrency_c*_summary.csv files found. Skipping concurrency plots.")
        return

    x = [r["concurrency"] for r in rows]

    metrics = [
        ("throughput_qps", "QPS", "Week2 QPS vs Concurrency", "week2_qps_vs_concurrency.png"),
        ("client_latency_p50", "P50 Latency (s)", "Week2 P50 Latency vs Concurrency", "week2_p50_vs_concurrency.png"),
        ("client_latency_p95", "P95 Latency (s)", "Week2 P95 Latency vs Concurrency", "week2_p95_vs_concurrency.png"),
        ("tokens_per_second_avg", "Tokens/s", "Week2 Tokens/s vs Concurrency", "week2_tokens_per_second_vs_concurrency.png"),
        ("error_rate", "Error Rate", "Week2 Error Rate vs Concurrency", "week2_error_rate_vs_concurrency.png"),
    ]

    for key, ylabel, title, filename in metrics:
        y_pairs = [(r["concurrency"], r[key]) for r in rows if r[key] is not None]
        if not y_pairs:
            print(f"No data for {key}. Skipping.")
            continue

        plot_line(
            x=[p[0] for p in y_pairs],
            y=[p[1] for p in y_pairs],
            xlabel="Concurrency",
            ylabel=ylabel,
            title=title,
            output=figures_dir / filename,
        )
        print(f"saved: {figures_dir / filename}")


def plot_context_length(results_dir: Path, figures_dir: Path) -> None:
    path = results_dir / "week2_context_length_benchmark.csv"

    if not path.exists():
        print("No week2_context_length_benchmark.csv found. Skipping context plots.")
        return

    rows = read_csv(path)

    parsed = []
    for r in rows:
        input_tokens = to_float(r.get("input_tokens"))
        latency = to_float(r.get("client_latency_seconds"))
        tokens_per_second = to_float(r.get("tokens_per_second"))
        ok = str(r.get("ok", "")).lower() == "true"

        if input_tokens is None:
            continue

        parsed.append(
            {
                "input_tokens": input_tokens,
                "latency": latency,
                "tokens_per_second": tokens_per_second,
                "ok": 1.0 if ok else 0.0,
            }
        )

    parsed.sort(key=lambda r: r["input_tokens"])

    if not parsed:
        print("No valid context-length rows found.")
        return

    x = [r["input_tokens"] for r in parsed]

    if any(r["latency"] is not None for r in parsed):
        y_pairs = [(r["input_tokens"], r["latency"]) for r in parsed if r["latency"] is not None]
        plot_line(
            [p[0] for p in y_pairs],
            [p[1] for p in y_pairs],
            "Input Tokens",
            "Latency (s)",
            "Week2 Latency vs Context Length",
            figures_dir / "week2_latency_vs_context_length.png",
        )
        print(f"saved: {figures_dir / 'week2_latency_vs_context_length.png'}")

    if any(r["tokens_per_second"] is not None for r in parsed):
        y_pairs = [
            (r["input_tokens"], r["tokens_per_second"])
            for r in parsed
            if r["tokens_per_second"] is not None
        ]
        plot_line(
            [p[0] for p in y_pairs],
            [p[1] for p in y_pairs],
            "Input Tokens",
            "Tokens/s",
            "Week2 Tokens/s vs Context Length",
            figures_dir / "week2_tokens_per_second_vs_context_length.png",
        )
        print(f"saved: {figures_dir / 'week2_tokens_per_second_vs_context_length.png'}")

    plot_line(
        x,
        [r["ok"] for r in parsed],
        "Input Tokens",
        "Success Flag",
        "Week2 Success vs Context Length",
        figures_dir / "week2_success_vs_context_length.png",
    )
    print(f"saved: {figures_dir / 'week2_success_vs_context_length.png'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Week2 benchmark results.")
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--figures-dir", default="figures")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    figures_dir = Path(args.figures_dir)

    plot_concurrency(results_dir, figures_dir)
    plot_context_length(results_dir, figures_dir)


if __name__ == "__main__":
    main()
