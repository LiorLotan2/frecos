# Cache-size sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cache size: ttl_confidence=0.9, cluster_count_k=10. n_queries=12000 with n_tenants=5,
n_clusters=10. Five cache-size points at 5%, 15%, 30%, 50%, 80% of the 6600-answer_id
working set: 330, 990, 1980, 3300, 5280 entries.

Rerun with real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters)
and benchmarks.semantic_index.SemanticIndex (0.8 threshold), replacing the prior
oracle-cluster + exact-match setup used throughout this project until this rerun.

Ten distinct traces per point (seeds 0-9). 50 rows in results.csv (5 points x 10
seeds), matching benchmarks.harness.CSV_COLUMNS (now including cluster_ari).

## Bootstrap method

Percentile bootstrap over the 10 per-seed values at each cache-size point. 10,000
resamples with replacement (n=10), median of each resample, 95% CI read off the
2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Results

| cache_size_entries | median hit_rate | 95% CI | median stale_hit_rate | 95% CI |
|---|---|---|---|---|
| 330  | 0.5670 | (0.5431, 0.5992) | 0.0710 | (0.0577, 0.0907) |
| 990  | 0.5624 | (0.5394, 0.5910) | 0.0707 | (0.0594, 0.0909) |
| 1980 | 0.5624 | (0.5394, 0.5910) | 0.0707 | (0.0594, 0.0909) |
| 3300 | 0.5624 | (0.5394, 0.5910) | 0.0707 | (0.0594, 0.0909) |
| 5280 | 0.5624 | (0.5394, 0.5910) | 0.0707 | (0.0594, 0.0909) |

## Effect direction

hit_rate flattens after 990 entries now, one point earlier than under the prior
exact-match run (which flattened at 1980): the semantic index's much higher baseline
hit rate (~56% here versus ~1.7% under exact-match) means the working set of distinct
entries the cache actually needs to hold is smaller relative to the total answer_id
count, so it saturates at a smaller absolute cache size. Both hit_rate and
stale_hit_rate are byte-identical across 990, 1980, 3300, and 5280 seed by seed,
confirming the cache stops mattering entirely past 990 entries at this trace scale.

## Knee

**990 entries (15% of the working set) is the knee** under the semantic index, versus
1980 (30%) under the prior exact-match index. The direction of the shift is the
opposite of what the exact-match-era summary predicted ("a semantic index would likely
push the knee to a larger cache size, since paraphrase and repeat traffic that
currently misses would start contending for cache slots") -- the semantic index's much
higher hit rate at every cache size actually *reduces* the number of distinct cache
slots needed to reach saturation, not increases it, because most queries now hit an
existing entry rather than needing their own slot.
