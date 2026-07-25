"""Figure 3: the correctness/efficiency trade-off as ttl_confidence varies.

From results/sweeps/ttl_confidence/results.csv. This is the honest core of
the project per the plan: the gate lowers hit rate by construction, so the
point of this figure is the shape of the exchange rate, not a claim that
either metric "wins". Plotted as two lines against ttl_confidence rather
than one metric against the other, since that is the form the underlying
sweep was run in and it makes the asymmetry (stale_hit_rate falls much
faster than hit_rate rises) directly visible from the two slopes.
"""
from common import load_csv, group_values, bootstrap_median_ci, new_figure, save_figure, REPO_ROOT

CONFIDENCES = ["0.8", "0.9", "0.95", "0.99"]


def main():
    rows = load_csv(REPO_ROOT / "results/sweeps/ttl_confidence/results.csv")
    stale_groups = group_values(rows, lambda r: r["ttl_confidence"], "stale_hit_rate")
    hit_groups = group_values(rows, lambda r: r["ttl_confidence"], "hit_rate")

    stale_stats = [bootstrap_median_ci(stale_groups[c]) for c in CONFIDENCES]
    hit_stats = [bootstrap_median_ci(hit_groups[c]) for c in CONFIDENCES]

    x = [float(c) for c in CONFIDENCES]

    fig, ax1 = new_figure()
    stale_med = [s[0] for s in stale_stats]
    stale_lo = [stale_med[i] - stale_stats[i][1] for i in range(4)]
    stale_hi = [stale_stats[i][2] - stale_med[i] for i in range(4)]
    l1 = ax1.errorbar(x, stale_med, yerr=[stale_lo, stale_hi], fmt="o-", capsize=4,
                       color="#c0392b", label="stale hit rate")
    ax1.set_xlabel("TTL confidence")
    ax1.set_ylabel("stale hit rate", color="#c0392b")
    ax1.tick_params(axis="y", labelcolor="#c0392b")

    ax2 = ax1.twinx()
    hit_med = [h[0] for h in hit_stats]
    hit_lo = [hit_med[i] - hit_stats[i][1] for i in range(4)]
    hit_hi = [hit_stats[i][2] - hit_med[i] for i in range(4)]
    l2 = ax2.errorbar(x, hit_med, yerr=[hit_lo, hit_hi], fmt="s--", capsize=4,
                       color="#2c3e50", label="hit rate")
    ax2.set_ylabel("hit rate", color="#2c3e50")
    ax2.tick_params(axis="y", labelcolor="#2c3e50")

    ax1.set_title("Trade-off: raising TTL confidence trades hit rate for staleness")
    ax1.legend(handles=[l1, l2], loc="upper center")
    fig.tight_layout()
    out = save_figure(fig, "fig3_ttl_confidence_tradeoff.png")
    print(out)


if __name__ == "__main__":
    main()
