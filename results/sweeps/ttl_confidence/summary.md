# A10 TTL-confidence sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
ttl_confidence: cache_size_entries=1980 (30% of the 6600-answer_id working set),
cluster_count_k=10. n_queries=12000, n_tenants=5, n_clusters=10, same trace generation
parameters as the cache-size sweep. Four confidence points exactly as specified:
0.8, 0.9, 0.95, 0.99. ttl_seconds = -ln(confidence) / lambda_c per cluster, so higher
confidence means a longer TTL (the gate tolerates more age before calling an entry stale).

Ten distinct traces per point (seeds 0-9), same rationale as the other two sweeps.

40 rows in results.csv (4 points x 10 seeds), matching benchmarks.harness.CSV_COLUMNS.

## Bootstrap method

Same as A8/cache_size: percentile bootstrap over the 10 per-seed values per point, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results: the (stale_hit_rate, hit_rate) trade-off pairs

| ttl_confidence | stale_hit_rate | 95% CI | hit_rate | 95% CI |
|---|---|---|---|---|
| 0.80 | 0.1263 | (0.1108, 0.1513) | 0.0192 | (0.0186, 0.0196) |
| 0.90 | 0.0420 | (0.0242, 0.0601) | 0.0174 | (0.0171, 0.0180) |
| 0.95 | 0.0227 | (0.0080, 0.0275) | 0.0170 | (0.0165, 0.0175) |
| 0.99 | 0.0079 | (0.0000, 0.0083) | 0.0163 | (0.0157, 0.0167) |

These four (stale_hit_rate, hit_rate) pairs, read down the table, are the trade-off curve:
as ttl_confidence rises from 0.80 to 0.99, stale_hit_rate drops from 0.1263 to 0.0079 (a
16x reduction) while hit_rate drops from 0.0192 to 0.0163 (a 15% reduction). The gate gets
much stricter about age at higher confidence -- shorter TTLs mean more entries get
rejected as stale before they can serve a hit -- and that strictness buys a large
reduction in stale hits for a comparatively small hit-rate cost.

## Effect direction

Both metrics are monotone decreasing as ttl_confidence increases, across all four points,
with no reversals. stale_hit_rate falls fastest between 0.80 and 0.90 (0.1263 -> 0.0420,
a drop of 0.084) and much more slowly after that (0.0420 -> 0.0227 -> 0.0079). hit_rate
falls roughly linearly and far more gently throughout (0.0192 -> 0.0174 -> 0.0170 ->
0.0163). The exchange rate is not uniform: most of the stale-hit-rate benefit of raising
confidence is captured by the first step, from 0.80 to 0.90, while hit_rate keeps eroding
at a steadier pace across the whole range.
