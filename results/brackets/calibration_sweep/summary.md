# Bracketing follow-up: calibration at scarcer sample size

## Verdict

Median cluster_ari is 0.41, close to the main run's 0.42 -- clustering quality is
essentially unaffected by trace size, as expected, since clustering is fit from query-text
embeddings, not from the number of calibration observations per cluster. learned (median
stale_hit_rate 0.062) is below global (0.110, p ~ 0.047, r ~ -0.76) and above oracle
(0.041), the latter not significant at n=5 (p ~ 0.076, r ~ 0.68). Neither comparison is
among the ones the report quotes, so neither is in the Holm-corrected family in
analysis/multiple_comparisons.py; both p-values here are raw.

The learned-vs-global gap is if anything a bit clearer here than in the main 3000-query
run, which is the question this follow-up exists to ask (does the gap widen when
calibration data is scarcer) -- though at 5 seeds this is a suggestive difference in
significance, not a claim about which scale shows a truer gap.

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

- learned vs global: U_a=3.0, p ~ 0.047, r ~ -0.76 (large effect, learned lower/better)
- learned vs oracle: U_a=21.0, p ~ 0.076, r ~ 0.68 (not significant at n=5, large effect, learned higher than oracle)
- global vs oracle: U_a=25.0, p ~ 0.009, r ~ 1.00 (perfect separation)

## Takeaway for the report

This follow-up asks whether scarcer calibration data widens the learned/oracle gap. Both
the main run and this scarcer-calibration run show the same qualitative pattern (learned
between global and oracle); this run's learned-vs-global comparison reaches raw
significance where the main 3000-query run's does not, though the main run's effect size,
r ~ -0.84, is larger. That is consistent with -- not proof of -- the hypothesis that
scarcer calibration makes the learned/global gap more visible; five seeds per condition
cannot distinguish "scarcer calibration widens the gap" from ordinary seed-to-seed
variation.
