# Cluster-count-K sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cluster_count_k: cache_size_entries=1980, ttl_confidence=0.9. n_queries=12000,
n_tenants=5. Four K points: 5, 10, 20, 50. n_clusters is varied at trace generation
time, so the ground-truth cluster structure itself changes per point.

Rerun with real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters)
and benchmarks.semantic_index.SemanticIndex (0.8 threshold), replacing the prior
oracle-cluster + exact-match setup. Ten distinct traces per point (seeds 0-9). 40 rows
in results.csv, matching benchmarks.harness.CSV_COLUMNS (now including cluster_ari).

## Bootstrap method

Percentile bootstrap over the 10 per-seed values per point, 10,000 resamples, median of
each resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded
12345.

## Results

| cluster_count_k | median hit_rate | 95% CI | median stale_hit_rate | 95% CI | median cluster_ari |
|---|---|---|---|---|---|
| 5  | 0.6032 | (0.5443, 0.6295) | 0.0615 | (0.0533, 0.0841) | 0.022 |
| 10 | 0.5624 | (0.5394, 0.5910) | 0.0707 | (0.0594, 0.0909) | 0.036 |
| 20 | 0.5630 | (0.5552, 0.5864) | 0.0744 | (0.0645, 0.0861) | 0.047 |
| 50 | 0.5975 | (0.5828, 0.6054) | 0.0779 | (0.0605, 0.0862) | 0.055 |

## Effect direction

hit_rate is non-monotone, dipping at K=10/20 and recovering at K=5 and K=50; the CIs
overlap heavily at every adjacent pair, same as under the prior exact-match run, so this
remains not distinguishable from noise at n=10 seeds. stale_hit_rate rises gently and
close to monotonically from K=5 to K=50 (0.0615 -> 0.0707 -> 0.0744 -> 0.0779), a
slightly cleaner trend than the exact-match era's up-then-down pattern, but the CIs
still overlap between every adjacent pair.

The clearer trend in this rerun is cluster_ari itself, which rises steadily with K
(0.022 at K=5 to 0.055 at K=50): more, smaller ground-truth clusters appear to be
marginally easier for k-means-on-embeddings to separate than fewer, larger ones, though
every value in this range is still far below what would count as good clustering
(ARI 1.0 is a perfect match; these are close to what a random assignment would produce).
This is consistent with, not contradicting, the central clustering-quality finding in
results/brackets/summary.md: cluster identity is not well recovered at any K tested
here, it is merely somewhat less badly recovered as K grows.
