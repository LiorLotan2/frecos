# Cluster-count-K sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cluster_count_k: cache_size_entries=495, ttl_confidence=0.9. n_queries=3000,
n_tenants=5 (reduced-scale rerun with the generator text fix, see
results/brackets/summary.md). Four K points: 5, 10, 20, 50. n_clusters is varied at
trace generation time, so the ground-truth cluster structure itself changes per point.

Five distinct traces per point (seeds 0-4). 20 rows in results.csv, matching
benchmarks.harness.CSV_COLUMNS (now including cluster_ari, n_useful_hits,
useful_hit_rate).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values per point, 10,000 resamples, median of
each resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded
12345.

## Results

| cluster_count_k | median hit_rate | 95% CI | median stale_hit_rate | 95% CI | median cluster_ari |
|---|---|---|---|---|---|
| 5  | 0.4037 | (0.3402, 0.4466) | 0.0778 | (0.0640, 0.1777) | 0.451 |
| 10 | 0.3360 | (0.2921, 0.3836) | 0.0677 | (0.0505, 0.0874) | 0.419 |
| 20 | 0.3407 | (0.3354, 0.3757) | 0.0820 | (0.0590, 0.1577) | 0.272 |
| 50 | 0.3307 | (0.3079, 0.3487) | 0.0804 | (0.0784, 0.1498) | 0.320 |

## Effect direction

hit_rate is non-monotone, highest at K=5 and roughly flat from K=10 onward; the CIs
overlap substantially at K=10/20/50, so hit_rate is not clearly distinguishable across
those three at n=5 seeds. stale_hit_rate is similarly non-monotone (0.078, 0.068,
0.082, 0.080), with wide, overlapping CIs at every point.

cluster_ari now shows the *opposite* trend from the pre-fix rerun: it is highest at
K=5 (0.451) and lowest at K=20 (0.272), rather than rising steadily with K. This is
not explained by topic-vocabulary exhaustion -- CLUSTER_TOPICS has 51 entries, more
than every K tested here (5/10/20/50), so every cluster gets a distinct topic phrase at
every K, no cycling occurs. The more likely explanation is the ordinary k-means
difficulty of separating more, smaller ground-truth clusters at a fixed calibration
sample size: at K=20 or K=50, each cluster's calibration slice is proportionally
smaller (n_queries and calibration fraction are unchanged across this sweep, so more
clusters means fewer calibration rows per cluster), giving k-means less signal per
centroid to converge on. At only 5 seeds per point, though, this is a plausible
reading of a non-monotone result with wide, overlapping CIs, not a confirmed effect --
a genuine investigation would need to hold calibration-observations-per-cluster fixed
while varying K, which this sweep does not do.

This result sits in a supplementary table (`analysis/figures/supplementary.csv`)
rather than a headline figure, consistent with the pre-fix rerun's choice, since it
still clears neither the effect-size nor confidence-interval bar the rest of this
report's headline figures meet.
