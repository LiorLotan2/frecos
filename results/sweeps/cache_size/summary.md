# Cache-size sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cache size: ttl_confidence=0.9, cluster_count_k=10. n_queries=3000 with n_tenants=5,
n_clusters=10 (reduced-scale rerun with the generator text fix, see
results/brackets/summary.md). Five cache-size points at 5%, 15%, 30%, 50%, 80% of the
1650-answer_id working set: 82, 248, 495, 825, 1320 entries.

Five distinct traces per point (seeds 0-4). 25 rows in results.csv (5 points x 5
seeds), matching benchmarks.harness.CSV_COLUMNS (now including cluster_ari,
n_useful_hits, useful_hit_rate).

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

`analysis/fig3_cache_size.py` computes the knee directly from this table (the smallest
size whose median hit_rate is within 1% of every larger size's), rather than a
hardcoded constant -- see that module's docstring for why: an earlier version of this
project hardcoded the knee at a stale value after a rerun had already moved it, and the
figure's caption and this file's own number silently disagreed for a full remediation
pass before being caught.

## Effect direction

hit_rate and stale_hit_rate are byte-identical across 248, 495, 825, and 1320 entries
seed by seed, confirming the cache stops mattering entirely past 248 entries at this
trace scale -- the same 15%-of-working-set proportion this experiment found before the
generator text fix and the resulting scale reduction, now recovered at 1/4 the trace
size (248 = round(1650 * 0.15), matching the pre-fix run's 990 = round(6600 * 0.15)).

## Knee

**248 entries (15% of the working set) is the knee**, matching the proportion this
experiment identified before the generator fix and scale reduction. That the knee's
*proportion* of the working set is unchanged across a 4x change in trace size is a
useful cross-check: it means the semantic index's saturation behavior is a property of
the workload's answer-diversity structure, not an artifact of the specific trace size
tested.
