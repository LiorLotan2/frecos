"""Figure 4: cache-size sweep with the knee marked.

From results/sweeps/cache_size/results.csv. The knee is computed here, not
hardcoded: the smallest cache size whose median hit_rate is within
KNEE_TOLERANCE (relative) of every larger size's median. Hardcoding this value
is exactly the bug this module used to have (KNEE_SIZE = 1980 / "30%" left in
place after a rerun had already moved the true knee to 990 / 15%, see
CHANGES.md) -- computing it from the same results.csv the plot itself reads
means the annotation cannot drift out of sync with the data again.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT

SIZES = ["82", "248", "495", "825", "1320"]
WORKING_SET_ANSWER_IDS = 1650
KNEE_TOLERANCE = 0.01  # relative difference in median hit_rate counted as "plateaued"


def find_knee(sizes, medians):
    for i in range(len(sizes)):
        if all(
            abs(medians[j] - medians[i]) <= KNEE_TOLERANCE * medians[i]
            for j in range(i, len(sizes))
        ):
            return sizes[i]
    return sizes[-1]


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/cache_size/results.csv")
    groups = group_values(rows, lambda r: r["cache_size_entries"], "hit_rate")
    stats = [bootstrap_median_ci(groups[s]) for s in SIZES]

    x = [int(s) for s in SIZES]
    med = [s[0] for s in stats]
    lo = [med[i] - stats[i][1] for i in range(len(SIZES))]
    hi = [stats[i][2] - med[i] for i in range(len(SIZES))]

    knee_size = find_knee(x, med)
    knee_pct = round(100 * knee_size / WORKING_SET_ANSWER_IDS)

    fig, ax = new_figure()
    ax.errorbar(x, med, yerr=[lo, hi], fmt="o-", capsize=4, color="#2c3e50")
    ax.axvline(knee_size, color="#c0392b", linestyle="--", linewidth=1.2)
    knee_y = med[x.index(knee_size)]
    ax.annotate(f"knee: {knee_size} entries\n({knee_pct}% of working set)",
                xy=(knee_size, knee_y), xytext=(knee_size + 250, knee_y - 0.0015),
                fontsize=10, color="#c0392b")
    ax.set_xlabel("cache size (entries)")
    ax.set_ylabel("hit rate (median, 95% CI)")
    fig.tight_layout()
    out = save_figure(fig, "fig3_cache_size_knee.png")
    print(out)
    print(f"knee={knee_size} ({knee_pct}% of {WORKING_SET_ANSWER_IDS}-entry working set)")


if __name__ == "__main__":
    main()
