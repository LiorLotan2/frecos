# Cache-size sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cache size: ttl_confidence=0.9, cluster_count_k=10. n_queries=3000 with n_tenants=5,
n_clusters=10 (the scale every experiment behind the report runs at, see
results/brackets/summary.md). Five cache-size points at 5%, 15%, 30%, 50%, 80% of the
1650-answer_id working set: 82, 248, 495, 825, 1320 entries.

Five distinct traces per point (seeds 0-4). 25 rows in results.csv (5 points x 5
seeds), matching benchmarks.harness.CSV_COLUMNS, including cluster_ari, n_useful_hits
and useful_hit_rate.

## Bootstrap method

Percentile bootstrap over the 5 per-seed values at each cache-size point. 10,000
resamples with replacement (n=5), median of each resample, 95% CI read off the
2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Results

| cache_size_entries | median hit_rate | 95% CI | median stale_hit_rate | 95% CI |
|---|---|---|---|---|
| 82   | 0.2651 | (0.2587, 0.3005) | 0.0892 | (0.0424, 0.0986) |
| 248  | 0.3360 | (0.2921, 0.3836) | 0.0677 | (0.0505, 0.0874) |
| 495  | 0.3360 | (0.2921, 0.3836) | 0.0677 | (0.0505, 0.0874) |
| 825  | 0.3360 | (0.2921, 0.3836) | 0.0677 | (0.0505, 0.0874) |
| 1320 | 0.3360 | (0.2921, 0.3836) | 0.0677 | (0.0505, 0.0874) |

`analysis/fig3_cache_size.py` computes the knee from this table (the smallest size whose
median hit_rate is within 1% of every larger size's) rather than from a hardcoded
constant, so the figure's caption and this file's number are both derived from the
committed CSV and cannot drift apart from it or from each other.

## Effect direction

hit_rate and stale_hit_rate are byte-identical across 248, 495, 825, and 1320 entries
seed by seed: past 248 entries the cache size stops affecting either metric at this trace
scale. Only the 82-entry point (5% of the working set) is capacity-limited, at
hit_rate 0.2651 against 0.3360 everywhere above the knee.

## Knee

**248 entries is the knee**, which is 15% of the 1650-answer_id working set
(248 = round(1650 * 0.15)). Saturation at a fraction of the working set rather than at
its full size follows from the semantic index's 0.8 cosine threshold: one resident entry
can serve every query whose embedding falls inside its neighborhood, so the number of
entries needed to cover the workload is set by answer diversity, not by the answer count.
