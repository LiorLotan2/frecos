# Bracketing follow-up: calibration at scarcer sample size

## Verdict

Median cluster_ari is 0.41, close to the main run's 0.42 -- clustering quality is
essentially unaffected by trace size, as expected, since clustering is fit from query-text
embeddings, not from the number of calibration observations per cluster. learned (median
stale_hit_rate 0.062) is below global (0.110, r ~ -0.76) and above oracle (0.041,
r ~ 0.68). Neither gap clears alpha = 0.05: learned vs global is p ~ 0.047 under
analysis/stats.py's normal approximation but p = 0.0556 under the exact permutation test at
n=5 per arm, and learned vs oracle is p ~ 0.076 normal, p = 0.0952 exact. Neither
comparison is among the ones the report quotes, so neither is in the Holm-corrected family
in analysis/multiple_comparisons.py; both p-values here are raw.

The question this follow-up exists to ask is whether scarcer calibration data widens the
learned/oracle gap. The answer is mixed and small either way: the median learned-oracle gap
is marginally wider here than in the main 3000-query run (0.0213 against 0.0193, a 1.52x
against a 1.40x ratio), while the rank separation behind it is weaker (U_a=21.0, r ~ 0.68
against U_a=24.0, r ~ 0.92). The learned-vs-global gap is weaker here on both measures
(r ~ -0.76 against -0.84, exact p = 0.0556 against 0.0317), and the main run's is the one
that clears alpha = 0.05. At 5 seeds per arm none of these differences separates a real
scale effect from seed-to-seed variation.

## Setup

Same design as the main bracketing experiment: W1 eval split, gate enabled, FreCoS
eviction, ttl_confidence=0.9, cluster_count_k=10, three lambda_source values x 5 seeds,
but n_queries=1800 instead of 3000 and cache_size_entries=248 (the scarcer-calibration
design this follow-up exists for, independent of the main run's scale — see this runner's
module docstring). Per-cluster calibration observations at this scale range 41-70 across
the 5 seeds, close to the fitter's MIN_OBSERVATIONS=30 fallback floor
(gptcache_ext/staleness/fitter.py).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | median cluster_ari | median false_hit_rate |
|---|---|---|---|---|---|
| global | 0.1096 | (0.0833, 0.1483) | 0.103 | 0.407 | 0.904 |
| learned | 0.0623 | (0.0446, 0.0955) | 0.119 | 0.407 | 0.895 |
| oracle | 0.0410 | (0.0284, 0.0578) | 0.121 | 0.407 | 0.907 |

Mann-Whitney U, stale_hit_rate. None of these three comparisons is in the report's
Holm-corrected family (analysis/multiple_comparisons.py), so every p below is raw.
p_normal is analysis/stats.py's two-sided normal approximation, the implementation behind
every p-value in this project; p_exact is the two-sided permutation p over all 252
arrangements of n_a = n_b = 5. Both are quoted because at this sample size they straddle
0.05, and the exact one governs.

- learned vs global: U_a=3.0, p_normal ~ 0.047, p_exact = 0.0556, r ~ -0.76 (large effect, learned lower/better, but does not clear alpha = 0.05)
- learned vs oracle: U_a=21.0, p_normal ~ 0.076, p_exact = 0.0952, r ~ 0.68 (large effect, learned higher than oracle, does not clear alpha = 0.05)
- global vs oracle: U_a=25.0, p_normal ~ 0.009, p_exact = 0.0079, r ~ 1.00 (perfect separation, the only one significant here, under either test)

## Takeaway for the report

This follow-up asks whether scarcer calibration data widens the learned/oracle gap. Both
the main run and this scarcer-calibration run show the same qualitative pattern, learned
between global and oracle, and scarcer calibration does not sharpen either separation:
learned vs global is weaker here than in the main 3000-query run on both measures
(r ~ -0.76 against -0.84, exact p = 0.0556 against 0.0317), and only the main run's clears
alpha = 0.05, while learned vs oracle has a marginally wider median gap here but a weaker
rank separation (r ~ 0.68 against 0.92). The honest reading is that five seeds per
condition cannot distinguish any effect of calibration sample size from ordinary
seed-to-seed variation, in either direction.
