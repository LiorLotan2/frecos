"""Figure 2: the bracket, global/learned/oracle lambda on one axis.

From results/brackets/results.csv. The calibration_sweep robustness check
(results/brackets/calibration_sweep/results.csv, a rerun at ~10x sparser
per-cluster calibration) is overlaid as a second set of points rather than a
separate figure, since it is the same three-way comparison at a different
sample size and the point of showing it is exactly that the picture doesn't
change.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT

ORDER = ["global", "learned", "oracle"]


def stats_for(path, key_col="lambda_source"):
    rows = load_csv(path)
    groups = group_values(rows, lambda r: r[key_col], "stale_hit_rate")
    return {k: bootstrap_median_ci(groups[k]) for k in ORDER}


def main():
    main_stats = stats_for(REPO_ROOT / "results/brackets/results.csv")
    calib_stats = stats_for(REPO_ROOT / "results/brackets/calibration_sweep/results.csv")

    fig, ax = new_figure()
    x = range(len(ORDER))

    med = [main_stats[k][0] for k in ORDER]
    lo = [med[i] - main_stats[ORDER[i]][1] for i in range(3)]
    hi = [main_stats[ORDER[i]][2] - med[i] for i in range(3)]
    ax.errorbar(x, med, yerr=[lo, hi], fmt="o-", capsize=5, color="#2c3e50",
                markersize=8, label="n_queries=3000 (main)")

    x2 = [xi + 0.12 for xi in x]
    med2 = [calib_stats[k][0] for k in ORDER]
    lo2 = [med2[i] - calib_stats[ORDER[i]][1] for i in range(3)]
    hi2 = [calib_stats[ORDER[i]][2] - med2[i] for i in range(3)]
    ax.errorbar(x2, med2, yerr=[lo2, hi2], fmt="s--", capsize=5, color="#c0392b",
                markersize=7, label="n_queries=1800 (sparser calibration)")

    ax.set_xticks(list(x))
    ax.set_xticklabels(["global", "learned", "oracle"])
    ax.set_ylabel("stale-hit-rate (median, 95% CI)")
    ax.legend()
    fig.tight_layout()
    out = save_figure(fig, "fig1_brackets.png")
    print(out)


if __name__ == "__main__":
    main()
