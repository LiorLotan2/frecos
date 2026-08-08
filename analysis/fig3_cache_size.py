"""Figure 3 in the report (label fig:cachesize): cache-size sweep with the knee
marked.

From results/sweeps/cache_size/results.csv. The knee is computed here, not
hardcoded: the smallest cache size whose median hit_rate is within
KNEE_TOLERANCE (relative) of every larger size's median. Deriving it from the
same results.csv the plot itself reads means the annotated knee and the plotted
curve cannot disagree, which a hardcoded constant would allow whenever the
underlying results change.
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

    fig, ax = new_figure(small=True)
    ax.errorbar(x, med, yerr=[lo, hi], fmt="o-", capsize=4, color="#2c3e50")
    ax.axvline(knee_size, color="#c0392b", linestyle="--", linewidth=1.2)
    # Axes-fraction placement, not data coordinates: at this figure's rendered width the
    # long form of this label ran past the right spine and sat on top of the plateau.
    # The caption carries the full sentence; the annotation only has to mark the line.
    ax.annotate(f"knee: {knee_size} entries ({knee_pct}%)",
                xy=(0.30, 0.06), xycoords="axes fraction",
                fontsize=10, color="#c0392b")
    ax.set_xlabel("cache size (entries)")
    ax.set_ylabel("hit rate (median, 95% CI)")
    fig.tight_layout()
    out = save_figure(fig, "fig3_cache_size_knee.png")
    print(out)
    print(f"knee={knee_size} ({knee_pct}% of {WORKING_SET_ANSWER_IDS}-entry working set)")


if __name__ == "__main__":
    main()
