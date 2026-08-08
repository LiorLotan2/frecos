"""Generates analysis/figures/supplementary.csv: summary statistics for
results that do not clear the bar for a headline figure (largest effect
size, tightest CI). Currently just the cluster_k sweep, which is
non-monotone with heavily overlapping CIs at every point (see
results/sweeps/cluster_k/summary.md) and so gets a table rather than a plot.
"""
import csv
from common import load_csv, group_values, bootstrap_median_ci, REPO_ROOT, FIGURES_DIR

K_VALUES = ["5", "10", "20", "50"]


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/cluster_k/results.csv")
    hit_groups = group_values(rows, lambda r: r["cluster_count_k"], "hit_rate")
    stale_groups = group_values(rows, lambda r: r["cluster_count_k"], "stale_hit_rate")

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = FIGURES_DIR / "supplementary.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["source", "cluster_count_k", "metric", "median", "ci_lo", "ci_hi"])
        for k in K_VALUES:
            hit_med, hit_lo, hit_hi = bootstrap_median_ci(hit_groups[k])
            writer.writerow(["sweeps/cluster_k", k, "hit_rate", hit_med, hit_lo, hit_hi])
            stale_med, stale_lo, stale_hi = bootstrap_median_ci(stale_groups[k])
            writer.writerow(
                ["sweeps/cluster_k", k, "stale_hit_rate", stale_med, stale_lo, stale_hi]
            )
    print(out_path)


if __name__ == "__main__":
    main()
