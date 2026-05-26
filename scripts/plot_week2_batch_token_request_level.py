from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


OUTPUT_DIR = Path("figures/week2/batch_tokens")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FILES = {
    "8192_c8": Path("results/week2_batch_tokens_8192_c8_benchmark_20260525.csv"),
    "32768_c8": Path("results/week2_batch_tokens_32768_c8_benchmark_20260525.csv"),
}


def find_column(df, candidates):
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(f"找不到候选列：{candidates}，当前列：{list(df.columns)}")


def load_data():
    frames = []
    for label, path in FILES.items():
        df = pd.read_csv(path)
        df["profile"] = label
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def plot_per_request_latency(df, latency_col):
    fig, ax = plt.subplots(figsize=(9, 4.8))

    for profile, marker in [("8192_c8", "o"), ("32768_c8", "x")]:
        sub = df[df["profile"] == profile].sort_values("case_id")
        ax.plot(sub["case_id"], sub[latency_col], marker=marker, label=profile)

    ax.axvspan(1, 8, alpha=0.15)
    ax.text(4.5, ax.get_ylim()[1] * 0.96, "first wave", ha="center", fontsize=10)

    ax.set_xlabel("case_id")
    ax.set_ylabel("Latency (s)")
    ax.set_title("32768 reduces first-wave tail latency under short-output c8")
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_path = OUTPUT_DIR / "week2_batch_tokens_short_c8_first_wave_latency.png"
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return output_path


def plot_wave_latency(df, latency_col):
    rows = []

    for profile in ["8192_c8", "32768_c8"]:
        sub = df[df["profile"] == profile].sort_values("case_id").copy()
        sub["wave"] = ((sub["case_id"] - 1) // 8) + 1

        grouped = sub.groupby("wave")[latency_col].agg(["mean", "max"]).reset_index()
        grouped["profile"] = profile
        rows.append(grouped)

    wave_df = pd.concat(rows, ignore_index=True)

    fig, ax = plt.subplots(figsize=(8, 4.8))

    for profile, marker in [("8192_c8", "o"), ("32768_c8", "x")]:
        sub = wave_df[wave_df["profile"] == profile]
        ax.plot(sub["wave"], sub["mean"], marker=marker, label=f"{profile} mean")
        ax.plot(sub["wave"], sub["max"], marker=marker, linestyle="--", label=f"{profile} max")

    ax.set_xlabel("request wave, 8 concurrent requests per wave")
    ax.set_ylabel("Latency (s)")
    ax.set_title("Wave-level latency shows burst handling difference")
    ax.legend()
    ax.grid(True, alpha=0.3)

    output_path = OUTPUT_DIR / "week2_batch_tokens_short_c8_wave_latency.png"
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return output_path


def save_wave_summary(df, latency_col):
    rows = []

    for profile in ["8192_c8", "32768_c8"]:
        sub = df[df["profile"] == profile].sort_values("case_id").copy()
        sub["wave"] = ((sub["case_id"] - 1) // 8) + 1
        grouped = sub.groupby("wave")[latency_col].agg(["mean", "max", "min"]).reset_index()
        grouped.insert(0, "profile", profile)
        rows.append(grouped)

    summary = pd.concat(rows, ignore_index=True)
    output_path = Path("results/week2_batch_tokens_short_c8_wave_latency_summary_20260526.csv")
    summary.to_csv(output_path, index=False)
    return output_path


def main():
    df = load_data()
    latency_col = find_column(df, ["latency", "client_latency", "latency_seconds", "client_latency_seconds"])

    generated = [
        plot_per_request_latency(df, latency_col),
        plot_wave_latency(df, latency_col),
    ]

    summary_path = save_wave_summary(df, latency_col)

    print("===== 已生成 request-level 图表 =====")
    for path in generated:
        print(path)

    print("===== 已生成 wave summary =====")
    print(summary_path)


if __name__ == "__main__":
    main()
