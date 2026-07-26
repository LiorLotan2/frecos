# Misspecification bracket: Weibull half-life instead of exponential

## Verdict

Rerun with real embedder-based clustering and a semantic index. Same pattern as every
other bracket-style experiment in this rerun: learned tracks global (p ~ 0.82,
indistinguishable), not oracle (p ~ 0.0002, r ~ 0.85). The Weibull misspecification
this run was designed to test (an easier-than-exponential half-life distribution) is
now a second-order effect: the dominant factor is clustering quality (cluster_ari ~
0.041, in the same low range as every other experiment), which the half-life
distribution shape does not touch at all. cluster identity is determined entirely by
the query-text embedding step, upstream of and independent from how half_life is drawn.

## Setup

Same design as the main bracketing experiment: W1 eval split, gate enabled, FreCoS
eviction, cache_size_entries=1650, ttl_confidence=0.9, cluster_count_k=10, three
lambda_source values x 10 seeds. The only design change from the main run:
`generate_trace(..., half_life_shape=2.0)` draws each cluster's true half-life from a
Weibull distribution with the same mean scale as before but shape 2. Real clustering
(gptcache_ext.staleness.assign_real_clusters) and benchmarks.semantic_index.SemanticIndex
(0.8 threshold) replace the prior oracle-cluster + exact-match setup.

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | 95% CI | median n_hits | median false_hit_rate |
|---|---|---|---|---|---|---|
| global | 0.0270 | (0.0161, 0.0512) | 15.54 | (12.22, 18.39) | 4331.0 | 0.973 |
| learned | 0.0282 | (0.0144, 0.0458) | 15.57 | (12.20, 18.18) | 4317.0 | 0.972 |
| oracle | 0.0057 | (0.0046, 0.0076) | 16.01 | (12.39, 18.69) | 4305.5 | 0.973 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 47.0, p ~ 0.821, r ~ 0.05 (not significant)
- learned vs oracle: U = 100.0, p ~ 0.0002, r ~ 0.85 (significant, large effect)
- global vs oracle: U = 97.0, p ~ 0.0004, r ~ 0.79 (significant, large effect)

## Takeaway for the report

Under real clustering, the Weibull misspecification's original lesson (a
less-variable half-life distribution is easier to predict, so it under-tests the
fitter) is subsumed by the clustering-quality finding: learned cannot approach oracle
here regardless of how the half-life distribution is shaped, because the fitter is
already operating on the wrong clusters before it ever sees a half-life sample. This
result adds no new information beyond the main bracketing rerun and results/brackets/
mixture/, which tests the harder adversarial case; it confirms the pattern is not
specific to one half-life distribution.
