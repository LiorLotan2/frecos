"""Figure 3: the correctness/efficiency trade-off as ttl_confidence varies.

From results/sweeps/ttl_confidence/results.csv. Two stacked panels sharing an x-axis
rather than one plot with dual y-axes: stale_hit_rate falls by roughly 18x over this
range while useful-fraction-of-hits barely moves through 0.95, and independent axes on
one plot would let the two curves visually "cross" at a scale that implies a false
parity between them. Separate panels with independent, honestly-scaled y-axes avoid
that. The lower panel plots useful-fraction-of-hits (correct, non-stale hits over hits
served, not over all scored queries): with false_hit_rate now a large, real number under
the semantic index, the all-scored-queries definition an earlier version of this figure
used can go negative (it subtracts n_stale + n_false, which together can exceed n_hits),
so this is scoped to hits served instead.
"""
from common import load_csv, group_values, bootstrap_median_ci, save_figure, REPO_ROOT
import matplotlib.pyplot as plt

CONFIDENCES = ["0.8", "0.9", "0.95", "0.99"]


def useful_fraction_of_hits(row):
    n_hits = int(row["n_hits"])
    if n_hits == 0:
        return 0.0
    n_useful = max(n_hits - int(row["n_stale_hits_served"]) - int(row["n_false_hits"]), 0)
    return n_useful / n_hits


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/ttl_confidence/results.csv")
    stale_groups = group_values(rows, lambda r: r["ttl_confidence"], "stale_hit_rate")
    useful_groups = {}
    for row in rows:
        useful_groups.setdefault(row["ttl_confidence"], []).append(useful_fraction_of_hits(row))

    stale_stats = [bootstrap_median_ci(stale_groups[c]) for c in CONFIDENCES]
    useful_stats = [bootstrap_median_ci(useful_groups[c]) for c in CONFIDENCES]

    x = [float(c) for c in CONFIDENCES]

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(7.0, 5.5))

    stale_med = [s[0] for s in stale_stats]
    stale_lo = [stale_med[i] - stale_stats[i][1] for i in range(4)]
    stale_hi = [stale_stats[i][2] - stale_med[i] for i in range(4)]
    ax1.errorbar(
        x, stale_med, yerr=[stale_lo, stale_hi], fmt="o-", capsize=4, color="#c0392b",
    )
    ax1.set_ylabel("stale-hit-rate")

    useful_med = [h[0] for h in useful_stats]
    useful_lo = [useful_med[i] - useful_stats[i][1] for i in range(4)]
    useful_hi = [useful_stats[i][2] - useful_med[i] for i in range(4)]
    ax2.errorbar(
        x, useful_med, yerr=[useful_lo, useful_hi], fmt="s--", capsize=4, color="#2c3e50",
    )
    ax2.set_ylabel("useful-fraction-of-hits")
    ax2.set_xlabel("TTL confidence")

    fig.tight_layout()
    out = save_figure(fig, "fig4_ttl_confidence_tradeoff.png")
    print(out)


if __name__ == "__main__":
    main()
