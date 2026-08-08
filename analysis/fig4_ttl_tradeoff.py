"""Figure 3: the correctness/efficiency trade-off as ttl_confidence varies.

From results/sweeps/ttl_confidence/results.csv. Two stacked panels sharing an x-axis
rather than one plot with dual y-axes: stale_hit_rate and useful_hit_rate move on very
different scales over this range, and independent axes on one plot would let the two
curves visually "cross" at a scale that implies a false parity between them. Separate
panels with independent, honestly-scaled y-axes avoid that.

The lower panel plots useful_hit_rate directly from the harness (benchmarks.metrics.
useful_hit_rate / is_useful_hit): the fraction of served hits that were both correct
and fresh. An earlier version of this figure recomputed this as
n_hits - n_stale_hits_served - n_false_hits, which double-subtracts once a hit can be
both stale and false (is_stale_hit and is_false_hit are independent, overlapping
predicates), and can go negative -- hidden by a max(..., 0) clamp that made the value
read as measured zero rather than floored. Reading useful_hit_rate straight from the
CSV avoids reconstructing a union from two possibly-overlapping counts at all.
"""
from common import (
    load_csv, group_values, bootstrap_median_ci, save_figure, REPO_ROOT,
    FIG_WIDTH_SMALL, FIG_HEIGHT_SMALL,
)
import matplotlib.pyplot as plt

CONFIDENCES = ["0.8", "0.9", "0.95", "0.99"]


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/ttl_confidence/results.csv")
    stale_groups = group_values(rows, lambda r: r["ttl_confidence"], "stale_hit_rate")
    useful_groups = group_values(rows, lambda r: r["ttl_confidence"], "useful_hit_rate")

    stale_stats = [bootstrap_median_ci(stale_groups[c]) for c in CONFIDENCES]
    useful_stats = [bootstrap_median_ci(useful_groups[c]) for c in CONFIDENCES]

    x = [float(c) for c in CONFIDENCES]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, sharex=True, figsize=(FIG_WIDTH_SMALL, FIG_HEIGHT_SMALL * 1.5)
    )

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
    ax2.set_ylabel("useful-hit-rate")
    ax2.set_xlabel("TTL confidence")

    fig.tight_layout()
    out = save_figure(fig, "fig4_ttl_confidence_tradeoff.png")
    print(out)


if __name__ == "__main__":
    main()
