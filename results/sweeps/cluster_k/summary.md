# Cluster-count-K sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cluster_count_k: cache_size_entries=1980, ttl_confidence=0.9. n_queries=12000, n_tenants=5.
Four K points exactly as specified: 5, 10, 20, 50. n_clusters is varied at trace
generation time (workloads.w1_synthetic.generator.generate_trace(n_clusters=k, ...)), so
the ground-truth cluster structure itself changes per point, not just a downstream
relabeling. The staleness table is fit with mode="learned" against whichever cluster_ids
appear in that trace, so the number of clusters the fitter and gate see follows directly
from generation and needed no separate wiring.

Ten distinct traces per point (seeds 0-9), same rationale as the other two sweeps.

40 rows in results.csv (4 points x 10 seeds), matching benchmarks.harness.CSV_COLUMNS.

## Bootstrap method

Same as the other two sweeps: percentile bootstrap over the 10 per-seed values per point,
10,000 resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles.
Python stdlib random, seeded 12345.

## Results

| cluster_count_k | median hit_rate | 95% CI | median stale_hit_rate | 95% CI |
|---|---|---|---|---|
| 5  | 0.0183 | (0.0177, 0.0187) | 0.0326 | (0.0217, 0.0488) |
| 10 | 0.0174 | (0.0171, 0.0180) | 0.0420 | (0.0242, 0.0601) |
| 20 | 0.0164 | (0.0156, 0.0180) | 0.0477 | (0.0229, 0.0596) |
| 50 | 0.0178 | (0.0161, 0.0188) | 0.0341 | (0.0224, 0.0618) |

## Effect direction

Non-monotone on both metrics. hit_rate goes 0.0183 -> 0.0174 -> 0.0164 -> 0.0178 as K goes
5 -> 10 -> 20 -> 50: it dips through the middle two points and partially recovers at K=50.
stale_hit_rate goes 0.0326 -> 0.0420 -> 0.0477 -> 0.0341, rising through K=5/10/20 and then
dropping back down at K=50. Neither series moves in one direction across the full range,
and the confidence intervals overlap heavily at every adjacent pair (e.g. hit_rate at
K=10 and K=20: (0.0171, 0.0180) vs (0.0156, 0.0180)), so none of these differences look
distinguishable from noise given only 10 seeds per point.

This is a genuinely different pattern from the other two axes, which were both clean
monotone effects. A plausible explanation: with n_queries fixed at 12000 and n_tenants=5,
increasing K spreads the same query volume over more (smaller) per-cluster calibration
samples, so the learned lambda per cluster gets noisier as K grows, while at the same time
more clusters means finer-grained TTLs that could in principle help. Those two effects
pull in opposite directions and appear to roughly cancel out at this trace size, which is
consistent with there being no clear winner in the table above. A larger n_queries per
point, or more seeds, would be needed to say anything sharper about the direction of the
K effect; at this sample size the honest conclusion is that cluster count does not have a
detectable monotone effect on either metric in this workload.
