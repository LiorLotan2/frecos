"""Figure 3: the correctness/efficiency trade-off as ttl_confidence varies.

From results/sweeps/ttl_confidence/results.csv. Two stacked panels sharing an x-axis
rather than one plot with dual y-axes: stale_hit_rate falls by roughly 16x over this
range while hit_rate falls by roughly 15%, and independent axes on one plot would let the
two curves visually "cross" at a scale that implies a false parity between them. Separate
panels with independent, honestly-scaled y-axes avoid that.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT
import matplotlib.pyplot as plt

CONFIDENCES = ["0.8", "0.9", "0.95", "0.99"]


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/ttl_confidence/results.csv")
    stale_groups = group_values(rows, lambda r: r["ttl_confidence"], "stale_hit_rate")
    hit_groups = group_values(rows, lambda r: r["ttl_confidence"], "hit_rate")

    stale_stats = [bootstrap_median_ci(stale_groups[c]) for c in CONFIDENCES]
    hit_stats = [bootstrap_median_ci(hit_groups[c]) for c in CONFIDENCES]

    x = [float(c) for c in CONFIDENCES]

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(7.0, 5.5))

    stale_med = [s[0] for s in stale_stats]
    stale_lo = [stale_med[i] - stale_stats[i][1] for i in range(4)]
    stale_hi = [stale_stats[i][2] - stale_med[i] for i in range(4)]
    ax1.errorbar(
        x, stale_med, yerr=[stale_lo, stale_hi], fmt="o-", capsize=4, color="#c0392b",
    )
    ax1.set_ylabel("stale-hit-rate")

    hit_med = [h[0] for h in hit_stats]
    hit_lo = [hit_med[i] - hit_stats[i][1] for i in range(4)]
    hit_hi = [hit_stats[i][2] - hit_med[i] for i in range(4)]
    ax2.errorbar(
        x, hit_med, yerr=[hit_lo, hit_hi], fmt="s--", capsize=4, color="#2c3e50",
    )
    ax2.set_ylabel("hit rate")
    ax2.set_xlabel("TTL confidence")

    fig.tight_layout()
    out = save_figure(fig, "fig3_ttl_confidence_tradeoff.png")
    print(out)


if __name__ == "__main__":
    main()
