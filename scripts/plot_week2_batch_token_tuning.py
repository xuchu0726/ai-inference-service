from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# 输入：Week2 batch token 调优实验的汇总 CSV。
SUMMARY_PATH = Path("results/week2_batch_tokens_workload_summary_20260525.csv")

# 输出：用于报告展示的图表目录。
OUTPUT_DIR = Path("figures/week2/batch_tokens")


def add_bar_labels(ax, values, fmt="{:.3f}"):
    """在柱状图顶部标注数值。"""
    for bar, value in zip(ax.patches, values):
        ax.annotate(
            fmt.format(value),
            xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
        )


def save_line_plot(df, x_col, y_col, title, ylabel, output_name, value_fmt="{:.3f}"):
    """保存折线图，用于展示 sweep 趋势。"""
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(df[x_col], df[y_col], marker="o")
    ax.set_xlabel("max_num_batched_tokens")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)

    for x, y in zip(df[x_col], df[y_col]):
        ax.annotate(
            value_fmt.format(y),
            xy=(x, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=9,
        )

    fig.tight_layout()
    output_path = OUTPUT_DIR / output_name
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return output_path


def save_bar_plot(df, y_col, title, ylabel, output_name, value_fmt="{:.3f}"):
    """保存柱状图，用于展示候选配置对比。"""
    fig, ax = plt.subplots(figsize=(7, 4.5))
    values = df[y_col].tolist()
    ax.bar(df["max_num_batched_tokens"].astype(str), values)
    ax.set_xlabel("max_num_batched_tokens")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    add_bar_labels(ax, values, value_fmt)

    fig.tight_layout()
    output_path = OUTPUT_DIR / output_name
    fig.savefig(output_path, dpi=220)
    plt.close(fig)
    return output_path


def save_workload_p95_summary(df):
    """保存 P95 综合对比图，突出不同 workload 下的推荐配置差异。"""
    selected = df[df["scenario"].isin(["short_output_c8", "long_output_c4"])].copy()
    selected["label"] = (
        selected["scenario"]
        + "\n"
        + selected["max_num_batched_tokens"].astype(str)
    )

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    values = selected["latency_p95_s"].tolist()
    ax.bar(selected["label"], values)
    ax.set_ylabel("P95 latency (s)")
    ax.set_title("P95 latency shows workload-dependent batching behavior")
    add_bar_labels(ax, values, "{:.3f}")

    ax.text(
        0.5,
        -0.22,
        "Short-output c8 favors 32768; long-output c4 is more stable with 8192.",
        transform=ax.transAxes,
        ha="center",
        fontsize=10,
    )

    fig.tight_layout()
    output_path = OUTPUT_DIR / "week2_batch_tokens_workload_p95_summary.png"
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_workload_qps_summary(df):
    """保存 QPS 综合对比图，突出吞吐差异。"""
    selected = df[df["scenario"].isin(["short_output_c8", "long_output_c4"])].copy()
    selected["label"] = (
        selected["scenario"]
        + "\n"
        + selected["max_num_batched_tokens"].astype(str)
    )

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    values = selected["throughput_qps"].tolist()
    ax.bar(selected["label"], values)
    ax.set_ylabel("Throughput (QPS)")
    ax.set_title("Throughput comparison across workload profiles")
    add_bar_labels(ax, values, "{:.3f}")

    ax.text(
        0.5,
        -0.22,
        "32768 improves short-output burst throughput but does not improve long-output throughput.",
        transform=ax.transAxes,
        ha="center",
        fontsize=10,
    )

    fig.tight_layout()
    output_path = OUTPUT_DIR / "week2_batch_tokens_workload_qps_summary.png"
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def save_decision_table_figure(df):
    """保存策略结论图，用于报告中直接展示推荐 serving profile。"""
    short_c8_8192 = df[(df["scenario"] == "short_output_c8") & (df["max_num_batched_tokens"] == 8192)].iloc[0]
    short_c8_32768 = df[(df["scenario"] == "short_output_c8") & (df["max_num_batched_tokens"] == 32768)].iloc[0]
    long_c4_8192 = df[(df["scenario"] == "long_output_c4") & (df["max_num_batched_tokens"] == 8192)].iloc[0]
    long_c4_32768 = df[(df["scenario"] == "long_output_c4") & (df["max_num_batched_tokens"] == 32768)].iloc[0]

    short_qps_gain = (short_c8_32768["throughput_qps"] / short_c8_8192["throughput_qps"] - 1) * 100
    short_p95_drop = (1 - short_c8_32768["latency_p95_s"] / short_c8_8192["latency_p95_s"]) * 100
    long_qps_drop = (1 - long_c4_32768["throughput_qps"] / long_c4_8192["throughput_qps"]) * 100
    long_p95_increase = (long_c4_32768["latency_p95_s"] / long_c4_8192["latency_p95_s"] - 1) * 100

    lines = [
        "Workload-aware batching decision",
        "",
        f"Short-output c8: 32768 vs 8192",
        f"- QPS: {short_c8_32768['throughput_qps']:.3f} vs {short_c8_8192['throughput_qps']:.3f}  (+{short_qps_gain:.1f}%)",
        f"- P95: {short_c8_32768['latency_p95_s']:.3f}s vs {short_c8_8192['latency_p95_s']:.3f}s  (-{short_p95_drop:.1f}%)",
        f"- Recommended profile: short_output_burst -> 32768",
        "",
        f"Long-output c4: 8192 vs 32768",
        f"- QPS: {long_c4_8192['throughput_qps']:.3f} vs {long_c4_32768['throughput_qps']:.3f}  (+{long_qps_drop:.1f}% for 8192)",
        f"- P95: {long_c4_8192['latency_p95_s']:.3f}s vs {long_c4_32768['latency_p95_s']:.3f}s  (32768 is +{long_p95_increase:.1f}% higher)",
        f"- Recommended profile: long_output_or_mixed -> 8192",
    ]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.axis("off")
    ax.text(
        0.02,
        0.98,
        "\n".join(lines),
        va="top",
        ha="left",
        fontsize=12,
        family="monospace",
    )

    fig.tight_layout()
    output_path = OUTPUT_DIR / "week2_batch_tokens_profile_decision.png"
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def main():
    if not SUMMARY_PATH.exists():
        raise FileNotFoundError(f"找不到实验汇总文件：{SUMMARY_PATH}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(SUMMARY_PATH)

    short_c4 = df[df["scenario"] == "short_output_c4"].sort_values(
        "max_num_batched_tokens"
    )
    short_c8 = df[df["scenario"] == "short_output_c8"].sort_values(
        "max_num_batched_tokens"
    )
    long_c4 = df[df["scenario"] == "long_output_c4"].sort_values(
        "max_num_batched_tokens"
    )

    generated = []

    # 基础图：coarse sweep 趋势。
    generated.append(
        save_line_plot(
            short_c4,
            "max_num_batched_tokens",
            "throughput_qps",
            "Short-output c4 throughput sweep",
            "Throughput (QPS)",
            "week2_batch_tokens_short_c4_qps.png",
        )
    )
    generated.append(
        save_line_plot(
            short_c4,
            "max_num_batched_tokens",
            "latency_p95_s",
            "Short-output c4 P95 latency sweep",
            "P95 latency (s)",
            "week2_batch_tokens_short_c4_p95.png",
        )
    )

    # 基础图：候选配置对比。
    generated.append(
        save_bar_plot(
            short_c8,
            "throughput_qps",
            "Short-output c8 throughput comparison",
            "Throughput (QPS)",
            "week2_batch_tokens_short_c8_qps.png",
        )
    )
    generated.append(
        save_bar_plot(
            short_c8,
            "latency_p95_s",
            "Short-output c8 P95 latency comparison",
            "P95 latency (s)",
            "week2_batch_tokens_short_c8_p95.png",
        )
    )
    generated.append(
        save_bar_plot(
            long_c4,
            "throughput_qps",
            "Long-output c4 throughput comparison",
            "Throughput (QPS)",
            "week2_batch_tokens_long_c4_qps.png",
        )
    )
    generated.append(
        save_bar_plot(
            long_c4,
            "latency_p95_s",
            "Long-output c4 P95 latency comparison",
            "P95 latency (s)",
            "week2_batch_tokens_long_c4_p95.png",
        )
    )

    # 报告图：综合结论和 profile 决策。
    generated.append(save_workload_p95_summary(df))
    generated.append(save_workload_qps_summary(df))
    generated.append(save_decision_table_figure(df))

    print("===== 已生成图表 =====")
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
