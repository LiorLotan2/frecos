# TTL-confidence sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
ttl_confidence: cache_size_entries=1980, cluster_count_k=10. n_queries=12000,
n_tenants=5, n_clusters=10. Four confidence points: 0.8, 0.9, 0.95, 0.99.
ttl_seconds = -ln(confidence) / lambda_c per cluster.

Rerun with real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters)
and benchmarks.semantic_index.SemanticIndex (0.8 threshold), replacing the prior
oracle-cluster + exact-match setup. Ten distinct traces per point (seeds 0-9). 40 rows
in results.csv, matching benchmarks.harness.CSV_COLUMNS (now including cluster_ari).

## Bootstrap method

Percentile bootstrap over the 10 per-seed values per point, 10,000 resamples, median of
each resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded
12345.

## Results: the (stale_hit_rate, hit_rate) trade-off pairs

| ttl_confidence | stale_hit_rate | 95% CI | hit_rate | 95% CI |
|---|---|---|---|---|
| 0.80 | 0.1327 | (0.1201, 0.1608) | 0.6843 | (0.6668, 0.7008) |
| 0.90 | 0.0707 | (0.0594, 0.0909) | 0.5624 | (0.5394, 0.5910) |
| 0.95 | 0.0392 | (0.0283, 0.0498) | 0.4728 | (0.4440, 0.4796) |
| 0.99 | 0.0073 | (0.0054, 0.0094) | 0.2690 | (0.2479, 0.2725) |

As ttl_confidence rises from 0.80 to 0.99, stale_hit_rate drops from 0.1327 to 0.0073 (a
~18x reduction) while hit_rate drops from 0.6843 to 0.2690 (a much steeper ~61%
reduction than the prior exact-match run's 15%). The trade-off's qualitative shape is
unchanged from the exact-match era -- both metrics still fall monotonically as
confidence rises, with no reversals -- but the hit-rate cost of tightening the TTL is
far larger now, since a real semantic hit rate has much more absolute hit rate to lose.

## Effect direction

Both metrics remain monotone decreasing as ttl_confidence increases, across all four
points, with no reversals -- the gate's core mechanism still works correctly even
though the cluster assignments feeding its per-cluster TTL are poor quality (see
results/brackets/summary.md): a wrong lambda_c still produces a well-ordered ttl_seconds
as confidence varies, it is just fit against the wrong cluster's calibration data. This
sweep does not depend on cluster identity being *correct*, only on it being
*consistent* between calibration and serving, which real clustering still guarantees
even at low ARI (the same k-means assignment is used for both).
