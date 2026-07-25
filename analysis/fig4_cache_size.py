"""Figure 4: cache-size sweep with the knee marked.

From results/sweeps/cache_size/results.csv. The knee (1980 entries, 30% of
the 6600-answer_id working set) is already identified in that experiment's
summary.md by the slope-drop criterion described there; it is not
recomputed here, only marked on the plot.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT

SIZES = ["330", "990", "1980", "3300", "5280"]
KNEE_SIZE = 1980


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/cache_size/results.csv")
    groups = group_values(rows, lambda r: r["cache_size_entries"], "hit_rate")
    stats = [bootstrap_median_ci(groups[s]) for s in SIZES]

    x = [int(s) for s in SIZES]
    med = [s[0] for s in stats]
    lo = [med[i] - stats[i][1] for i in range(len(SIZES))]
    hi = [stats[i][2] - med[i] for i in range(len(SIZES))]

    fig, ax = new_figure()
    ax.errorbar(x, med, yerr=[lo, hi], fmt="o-", capsize=4, color="#2c3e50")
    ax.axvline(KNEE_SIZE, color="#c0392b", linestyle="--", linewidth=1.2)
    knee_y = med[SIZES.index(str(KNEE_SIZE))]
    ax.annotate("knee: 1980 entries\n(30% of working set)",
                xy=(KNEE_SIZE, knee_y), xytext=(KNEE_SIZE + 250, knee_y - 0.0015),
                fontsize=10, color="#c0392b")
    ax.set_xlabel("cache size (entries)")
    ax.set_ylabel("hit rate (median, 95% CI)")
    ax.set_title("Cache-size sweep: hit rate saturates past the knee")
    fig.tight_layout()
    out = save_figure(fig, "fig4_cache_size_knee.png")
    print(out)


if __name__ == "__main__":
    main()
