# Adversarial mixture bracket: two-rate half-life mixture instead of a single exponential

## Verdict

This is the genuinely hard misspecification case, and the first one in this project
where learned-vs-oracle produces a real, non-degenerate gap to measure. Learned still
separates from global at the same effect size as the well-specified run (U = 4.0,
p ~ 0.00051), but learned's median stale_hit_rate (0.0797) is now visibly, if not
significantly at n=10, above oracle's (0.0740): U = 59.0, p ~ 0.496. Learned tracks
oracle closely but is no longer identical to it seed by seed the way it was under a
matched or easier-than-matched half-life model, which is exactly what a genuinely
adversarial misspecification should produce.

## Setup

Same design as the original bracketing run and the Weibull misspecification attempt
(results/brackets/misspecified/): W1 eval split, gate enabled, FreCoS eviction,
cache_size_entries=1650, ttl_confidence=0.9, cluster_count_k=10, three lambda_source
values (global, learned, oracle) x 10 seeds (0-9) = 30 runs.

The change: `generate_trace(..., half_life_mode="mixture")` draws each cluster's true
half-life from a 50/50 mixture of two exponentials -- one at one-fifth of the cluster's
mean scale, one at 1.8 times it -- rather than a single exponential or a Weibull, while
keeping the same overall per-cluster mean as every other bracket run. A single MLE-fitted
exponential rate cannot be correct for both halves of a bimodal population at once, so
this case is harder for `fit_staleness_table` by construction, unlike the Weibull
attempt, which was accidentally easier. `oracle_lambdas_for_seed` still reconstructs
1/half_life_scale, the mixture's overall mean rate, since that is the best a
constant-hazard oracle table can encode; the mixture's bimodal shape has no equivalent
slot in this project's staleness table either.

results.csv has exactly 30 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly.

## Bootstrap method

Same as the other bracket runs: percentile bootstrap over the 10 per-seed values in each
lambda_source group, 10,000 resamples with replacement (n=10 each), median of each
resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Mann-Whitney U

Same hand-rolled implementation as the other bracket runs: ranks with average-rank tie
handling, U = R1 - n1(n1+1)/2, normal approximation for the p-value with the standard tie
correction to the variance term.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median n_hits | median n_stale_hits_served |
|---|---|---|---|---|
| global | 0.2083 | (0.1701, 0.2438) | 166.0 | 37.0 |
| learned | 0.0797 | (0.0707, 0.1002) | 142.0 | 11.0 |
| oracle | 0.0740 | (0.0672, 0.1032) | 142.0 | 11.0 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 4.0, p ~ 0.00051, r ~ 0.92 (significant, same effect size as the
  well-specified bracketing run)
- learned vs oracle: U = 59.0, p ~ 0.496, r ~ 0.18 (a small-to-moderate effect, not
  significant at n=10)

## Why hit counts differ from the well-specified run

Hit counts are higher here than in the well-specified bracketing run for every
lambda_source (166/142/142 versus 143/130/130.5 there): the short-scale half of the
mixture, at one-fifth of the cluster's mean half-life, makes more entries expire and get
regenerated, which changes what is resident in the cache at any given time. The two
runs' absolute hit rates are therefore not directly comparable; only the relative
ranking across lambda sources within each run is.

## Takeaway for the report

Taken together with the well-specified bracketing run and the (underpowered) Weibull
attempt, this is the third and hardest test of the same claim: per-cluster fitting beats
a single pooled rate by a large, significant margin, whether the true half-life
distribution is easier than the fitter assumes, exactly matches it, or is genuinely
adversarial to it. The learned-vs-oracle gap opening up (if not yet reaching significance
at n=10) under the adversarial mixture, after tracking oracle almost exactly everywhere
else in this project, is itself informative: it is the first evidence that the fitter's
exponential assumption has a real, measurable cost when that assumption is wrong in a
way that actually biases the MLE.
