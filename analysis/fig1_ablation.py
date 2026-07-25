"""Figure 1: stale-hit-rate by ablation row, the headline figure.

Rows 1-6 from results/ablation/results.csv. Per the plan, the comparison of
record is row 2 (LFU), not row 1 (LRU): Biton & Friedman's own finding is
that LRU is a weak baseline on semantic workloads, so grading against it
would flatter every other row trivially.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT

ROW_ORDER = [
    "ablation-w1-row1_lru",
    "ablation-w1-row2_lfu",
    "ablation-w1-row3_bf",
    "ablation-w1-row4_gate_lfu",
    "ablation-w1-row5_gate_frecos",
    "ablation-w1-row6_gate_frecos_nosize",
]
ROW_LABELS = {
    "ablation-w1-row1_lru": "1 LRU (stock)",
    "ablation-w1-row2_lfu": "2 LFU (floor)",
    "ablation-w1-row3_bf": "3 BF-sub",
    "ablation-w1-row4_gate_lfu": "4 gate+LFU",
    "ablation-w1-row5_gate_frecos": "5 gate+FreCoS",
    "ablation-w1-row6_gate_frecos_nosize": "6 gate+FreCoS(no-size)",
}
FLOOR_ROW = "ablation-w1-row2_lfu"


def main():
    rows = load_csv(REPO_ROOT / "results/ablation/results.csv")
    groups = group_values(rows, lambda r: r["run_id"].split("-seed")[0], "stale_hit_rate")

    medians, los, his = [], [], []
    for key in ROW_ORDER:
        med, lo, hi = bootstrap_median_ci(groups[key])
        medians.append(med)
        los.append(med - lo)
        his.append(hi - med)

    fig, ax = new_figure()
    x = range(len(ROW_ORDER))
    colors = ["#888888" if k != FLOOR_ROW else "#c0392b" for k in ROW_ORDER]
    ax.bar(x, medians, yerr=[los, his], capsize=4, color=colors)
    ax.set_xticks(list(x))
    ax.set_xticklabels([ROW_LABELS[k] for k in ROW_ORDER], rotation=12, ha="right")
    ax.set_ylabel("stale-hit-rate (median, 95% CI)")
    ax.axhline(
        medians[ROW_ORDER.index(FLOOR_ROW)], color="#c0392b", linestyle="--",
        linewidth=1, alpha=0.6, label="row 2 floor",
    )
    ax.legend()
    fig.tight_layout()
    out = save_figure(fig, "fig1_ablation_stale_hit_rate.png")
    print(out)


if __name__ == "__main__":
    main()
