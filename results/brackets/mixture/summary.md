# Adversarial mixture bracket: two-rate half-life mixture instead of a single exponential

## Verdict

Rerun with real embedder-based clustering and a semantic index. Same pattern as every
other bracket-style experiment in this rerun: learned tracks global (p ~ 0.65,
indistinguishable), not oracle (p ~ 0.0002, r ~ 0.83). This adversarial mixture -- true
half-life drawn from a bimodal two-rate mixture, deliberately hard for a single-rate
MLE -- was designed to test calibration quality, but clustering quality dominates here
too: cluster_ari is ~0.037, in the same low range as every other experiment, and it is
determined entirely by the query-text embedding step, independent of how half_life is
drawn.

## Setup

Same design as the main bracketing experiment and the misspecified run: W1 eval split,
gate enabled, FreCoS eviction, cache_size_entries=1650, ttl_confidence=0.9,
cluster_count_k=10, three lambda_source values x 10 seeds. The only design change:
`generate_trace(..., half_life_mode="mixture")` draws each cluster's true half-life
from a 50/50 mixture of two exponentials (one-fifth and 1.8x the cluster's mean scale).
Real clustering (gptcache_ext.staleness.assign_real_clusters) and
benchmarks.semantic_index.SemanticIndex (0.8 threshold) replace the prior oracle-cluster
+ exact-match setup.

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | 95% CI | median n_hits | median false_hit_rate |
|---|---|---|---|---|---|---|
| global | 0.1510 | (0.1218, 0.1659) | 14.20 | (10.97, 16.26) | 4352.0 | 0.970 |
| learned | 0.1423 | (0.1216, 0.1613) | 14.43 | (10.87, 16.21) | 4307.5 | 0.970 |
| oracle | 0.0949 | (0.0910, 0.1011) | 14.92 | (11.50, 17.05) | 4332.5 | 0.972 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 44.0, p ~ 0.650, r ~ 0.10 (not significant)
- learned vs oracle: U = 99.0, p ~ 0.0002, r ~ 0.83 (significant, large effect)
- global vs oracle: U = 99.0, p ~ 0.0002, r ~ 0.83 (significant, large effect)

## Takeaway for the report

Before this rerun, this was the one experiment where learned showed daylight from
oracle for the first time (rather than tracking it near-exactly), which was read as the
first sign that the fitter's exponential assumption had a measurable cost under a
genuinely adversarial true distribution. Under real clustering, that reading no longer
holds: learned is far from oracle here for the same structural reason it is far from
oracle everywhere else in this rerun (clustering, not calibration, is the bottleneck),
not because the mixture model is specifically harder to fit than the well-specified or
Weibull cases. All three bracket-style misspecification checks (well-specified,
Weibull, mixture) now show the identical qualitative pattern, which is itself
informative: the clustering-quality effect dominates regardless of what half-life
distribution the generator draws from.
