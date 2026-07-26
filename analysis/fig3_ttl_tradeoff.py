"""Figure 3: the correctness/efficiency trade-off as ttl_confidence varies.

From results/sweeps/ttl_confidence/results.csv. Two stacked panels sharing an x-axis
rather than one plot with dual y-axes: stale_hit_rate falls by roughly 16x over this
range while useful_hit_rate barely moves, and independent axes on one plot would let the
two curves visually "cross" at a scale that implies a false parity between them. Separate
panels with independent, honestly-scaled y-axes avoid that. The lower panel plots
useful-hit-rate rather than raw hit_rate: raw hit_rate falls steadily across the whole
range because the gate is converting stale hits into misses, which is the trade-off
working as designed, not a cost; useful-hit-rate (correct, non-stale hits over all scored
queries) isolates the part of that decline that is a real loss of service.
"""
from common import load_csv, group_values, bootstrap_median_ci, save_figure, REPO_ROOT
import matplotlib.pyplot as plt

CONFIDENCES = ["0.8", "0.9", "0.95", "0.99"]


def useful_hit_rate(row):
    return (
        (int(row["n_hits"]) - int(row["n_stale_hits_served"]) - int(row["n_false_hits"]))
        / int(row["n_queries"])
    )


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/ttl_confidence/results.csv")
    stale_groups = group_values(rows, lambda r: r["ttl_confidence"], "stale_hit_rate")
    useful_groups = {}
    for row in rows:
        useful_groups.setdefault(row["ttl_confidence"], []).append(useful_hit_rate(row))

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
    ax2.set_ylabel("useful-hit-rate")
    ax2.set_xlabel("TTL confidence")

    fig.tight_layout()
    out = save_figure(fig, "fig3_ttl_confidence_tradeoff.png")
    print(out)


if __name__ == "__main__":
    main()
