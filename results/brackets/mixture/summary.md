# Adversarial mixture bracket: two-rate half-life mixture instead of a single exponential

## Verdict

Rerun with the generator text fix (see results/brackets/summary.md for the root cause
and fix). Median cluster_ari is 0.40, close to the main run's 0.42 (a fresh trace at
this half_life_mode draws a substantially different rng sequence than the main run, so
distinct query texts differ, but the same vocabulary design keeps cluster signal
comparable). learned (median stale_hit_rate 0.154) is lower than global (0.189) with a
large effect, not significant at n=5 (p ~ 0.076, r ~ -0.68); learned is significantly
below oracle (0.120, p ~ 0.028, r ~ 0.84). Same qualitative pattern as the main run and
the Weibull misspecification check: per-cluster fitting helps, does not close the gap
to oracle, and the effect is directionally consistent but under-powered at 5 seeds for
the learned-vs-global comparison specifically.

## Setup

Same design as the main bracketing experiment and the misspecified run: W1 eval split,
gate enabled, FreCoS eviction, cache_size_entries=412, ttl_confidence=0.9,
cluster_count_k=10, three lambda_source values x 5 seeds. The only design change:
`generate_trace(..., half_life_mode="mixture")` draws each cluster's true half-life
from a 50/50 mixture of two exponentials (one-fifth and 1.8x the cluster's mean scale).
n_queries=3000, matching the reduced-scale rerun.

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | median cluster_ari | median false_hit_rate |
|---|---|---|---|---|---|
| global | 0.1889 | (0.1555, 0.2235) | 1.99 | 0.395 | 0.891 |
| learned | 0.1542 | (0.1244, 0.2193) | 1.97 | 0.395 | 0.896 |
| oracle | 0.1195 | (0.0992, 0.1447) | 1.95 | 0.395 | 0.908 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U_a=4.0, p ~ 0.076, r ~ -0.68 (not significant at n=5, large effect direction matches main run)
- learned vs oracle: U_a=23.0, p ~ 0.028, r ~ 0.84 (significant, large effect)
- global vs oracle: U_a=25.0, p ~ 0.009, r ~ 1.00 (significant, perfect separation)

## Takeaway for the report

The adversarial mixture (a genuinely harder case for a single-rate maximum-likelihood
fit than the well-specified or Weibull cases) shows the highest absolute
stale-hit-rate of the three misspecification checks at every lambda_source, as
expected -- the fitter's exponential assumption really is wrong here, and it costs
something. The relative pattern (learned between global and oracle) survives this
harder case, same as it survives the Weibull case, confirming clustering quality and
half-life misspecification are separate, additive sources of error rather than one
masking the other.
