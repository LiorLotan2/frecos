# Misspecification bracket: Weibull half-life instead of exponential

## Verdict

Median cluster_ari is 0.42, matching the main bracketing run. The pattern matches that
run too: learned (median stale_hit_rate 0.024) is lower than global (0.033) with a large
effect, though not significant even before correction (p ~ 0.175, r ~ -0.52 -- the
direction and magnitude match the main run, but 5 seeds gives this comparison less
power); learned is above oracle (0.003, p ~ 0.028, r ~ 0.84, learned worse than the
ceiling, as expected). Both comparisons are secondary (S2 and S3 in
analysis/multiple_comparisons.py) with Holm-adjusted p of 0.352 and 0.170, so neither
holds at alpha = 0.05. The Weibull misspecification this run tests (an
easier-than-exponential half-life distribution) is a second-order effect relative to
clustering quality.

## Setup

Same design as the main bracketing experiment: W1 eval split, gate enabled, FreCoS
eviction, cache_size_entries=412, ttl_confidence=0.9, cluster_count_k=10, three
lambda_source values x 5 seeds. The only design change from the main run:
`generate_trace(..., half_life_shape=2.0)` draws each cluster's true half-life from a
Weibull distribution with the same mean scale but shape 2. n_queries=3000 and 5 seeds,
the scale this experiment shares with brackets.py.

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | median cluster_ari | median false_hit_rate |
|---|---|---|---|---|---|
| global | 0.0333 | (0.0209, 0.0925) | 0.173 | 0.419 | 0.902 |
| learned | 0.0239 | (0.0071, 0.0611) | 0.177 | 0.419 | 0.920 |
| oracle | 0.0031 | (0.0018, 0.0089) | 0.173 | 0.419 | 0.919 |

Mann-Whitney U, stale_hit_rate (analysis/stats.py, rank-biserial r = 2*U_a/(n1*n2)-1).
p is raw; `make multiple-comparisons` prints the Holm-adjusted p of every comparison the
report quotes.

- learned vs global: U_a=6.0, p ~ 0.175, r ~ -0.52 (large effect, direction matches main run; secondary S2, adjusted p 0.352, does not hold)
- learned vs oracle: U_a=23.0, p ~ 0.028, r ~ 0.84 (large effect; secondary S3, adjusted p 0.170, does not hold)
- global vs oracle: U_a=25.0, p ~ 0.009, r ~ 1.00 (perfect separation; not among the comparisons the report quotes, so not in the corrected family)

## Takeaway for the report

The Weibull case's lesson is that a less-variable half-life distribution is easier to
predict, so it under-tests the fitter: absolute stale-hit-rate is lower here than in the
main well-specified bracket at every lambda_source, while the qualitative pattern --
learned below global, above oracle -- is the same. cluster_ari (0.42) is unaffected by the
half-life distribution's shape, as expected, since clustering is determined entirely by
query text embeddings, upstream of and independent from how half_life is drawn.
