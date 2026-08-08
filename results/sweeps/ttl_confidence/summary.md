# TTL-confidence sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
ttl_confidence: cache_size_entries=495, cluster_count_k=10. n_queries=3000, n_tenants=5,
n_clusters=10 (the scale every experiment behind the report runs at, see
results/brackets/summary.md). Four confidence points: 0.8, 0.9, 0.95, 0.99.
ttl_seconds = -ln(confidence) / lambda_c per cluster.

Five distinct traces per point (seeds 0-4). 20 rows in results.csv, matching
benchmarks.harness.CSV_COLUMNS, including cluster_ari, n_useful_hits and useful_hit_rate
(see "Useful-hit-rate" below for what the last one counts).

Eviction never fires in this sweep: against the 495-entry budget the resident set never
reaches capacity, and `select_victim` records zero calls at all four confidence points.
This sweep isolates the gate, the same way the ablation does
(results/ablation/summary.md).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values per point, 10,000 resamples, median of
each resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded
12345.

## Results: the (stale_hit_rate, hit_rate, useful_hit_rate) trade-off

| ttl_confidence | stale_hit_rate | hit_rate | useful_hit_rate | 95% CI (useful) | false_hit_rate |
|---|---|---|---|---|---|
| 0.80 | 0.1423 | 0.4862 | 0.0420 | (0.0348, 0.0619) | 0.9456 |
| 0.90 | 0.0677 | 0.3360 | 0.0801 | (0.0690, 0.1087) | 0.9111 |
| 0.95 | 0.0458 | 0.2312 | 0.1392 | (0.1161, 0.1726) | 0.8568 |
| 0.99 | 0.0000 | 0.0788 | 0.4581 | (0.3298, 0.5328) | 0.5419 |

As ttl_confidence rises from 0.80 to 0.99, stale_hit_rate falls to zero while hit_rate
falls from 0.49 to 0.08. false_hit_rate also falls substantially across the same range
(0.946 to 0.542): a tighter TTL expires stale entries sooner, which shrinks the pool of
entries available to match against at all, and with fewer (mostly correctly clustered)
entries surviving, a smaller fraction of hits are false. Cluster identity is recoverable
on this workload (median cluster_ari 0.42 across the sweep), so tightening the TTL
measurably improves correctness on two axes at once, staleness and false hits, at the
cost of hit rate.

## Useful-hit-rate: measured, not reconstructed

useful_hit_rate is read directly from the harness (benchmarks.metrics.useful_hit_rate /
is_useful_hit: a hit that is neither stale nor false), not reconstructed as
n_hits - n_stale_hits_served - n_false_hits. The reconstruction double-subtracts once a
hit can be both stale and false (the two predicates are independent and can overlap), and
clamping such a reconstruction at max(..., 0) would make an over-subtracted value read as
a measured zero rather than a floored one. Every value in the table above is a direct
count, so no clamp is applied anywhere in the path from harness to figure.

Mann-Whitney U, useful_hit_rate at 0.95 vs 0.99 (analysis/stats.py): U_a=0.0,
p ~ 0.0090, r ~ -1.00 (perfect separation, 0.99 strictly higher on every seed). This is
secondary comparison S10 in analysis/multiple_comparisons.py, Holm-adjusted p 0.090, so
it does not hold at alpha = 0.05; `make multiple-comparisons` prints it in context.

## Effect direction

Both stale_hit_rate and hit_rate remain monotone decreasing as ttl_confidence
increases, across all four points, with no reversals; useful_hit_rate and
false_hit_rate move monotonically in opposite directions to each other across the same
range. The gate's core mechanism behaves as designed, and because clustering on this
workload gives a usable (if imperfect) cluster signal, useful_hit_rate moves over a wide
enough range (0.042 to 0.458) for the trade-off against hit_rate to be measurable rather
than pinned near zero.
