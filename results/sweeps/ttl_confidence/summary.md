# TTL-confidence sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
ttl_confidence: cache_size_entries=495, cluster_count_k=10. n_queries=3000,
n_tenants=5, n_clusters=10 (reduced-scale rerun with the generator text fix, see
results/brackets/summary.md). Four confidence points: 0.8, 0.9, 0.95, 0.99.
ttl_seconds = -ln(confidence) / lambda_c per cluster.

Five distinct traces per point (seeds 0-4). 20 rows in results.csv, matching
benchmarks.harness.CSV_COLUMNS (now including cluster_ari, n_useful_hits,
useful_hit_rate -- the last two added alongside this rerun; see "Useful-hit-rate" below
for why).

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
(0.946 to 0.542): a tighter TTL evicts stale entries faster, which reduces the pool of
cached entries available to match against at all, and with fewer (mostly correctly
clustered) entries surviving, a smaller fraction of hits are false. This is a genuinely
different qualitative story than the pre-fix rerun found, where false_hit_rate sat
above 0.92 at every confidence level and useful_hit_rate was pinned near zero
throughout: with cluster identity now recoverable (median cluster_ari ~0.42 across this
sweep), tightening the TTL measurably improves correctness on two axes at once, not
just one.

## Useful-hit-rate: no longer clamped

useful_hit_rate is read directly from the harness (benchmarks.metrics.useful_hit_rate /
is_useful_hit: a hit that is neither stale nor false), not reconstructed as
n_hits - n_stale_hits_served - n_false_hits. The reconstruction double-subtracts once a
hit can be both stale and false (the two predicates are independent and can overlap),
and an earlier version of analysis/fig4_ttl_tradeoff.py clamped the reconstructed value
at max(..., 0), which made a genuinely negative (over-subtracted) value read as
measured zero rather than floored. Every value in the table above is >= 0 without any
clamp, confirming the direct-count approach avoids the double-subtraction bug rather
than merely hiding it.

Mann-Whitney U, useful_hit_rate at 0.95 vs 0.99 (analysis/stats.py): U_a=0.0,
p ~ 0.0090, r ~ -1.00 (perfect separation, 0.99 strictly higher on every seed).

## Effect direction

Both stale_hit_rate and hit_rate remain monotone decreasing as ttl_confidence
increases, across all four points, with no reversals; useful_hit_rate and
false_hit_rate move monotonically in opposite directions to each other across the same
range. The gate's core mechanism works correctly and, with real clustering now
providing a usable (if imperfect) cluster signal, the TTL sweep's effect on
useful_hit_rate is a genuine, measurable trade-off rather than a metric pinned at zero
by a workload with no separable clusters to serve correctly in the first place.
