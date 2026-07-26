# Misspecification bracket: Weibull half-life instead of exponential

## Verdict

Underpowered by construction, not by accident. The change (Weibull shape=2 in place of
the exponential's implicit shape=1, same per-cluster mean) has roughly half the
coefficient of variation of the exponential it replaces, which makes the workload's
staleness *easier* to predict, not harder. Every arm's stale_hit_rate improved relative
to the well-specified bracketing run (global: 0.144 -> 0.065; learned and oracle: 0.035
-> 0.000), and learned and oracle both floor at exactly zero rather than visibly
separating. That floor is a low-hit-count artifact, not evidence either estimator
handled misspecification well. This attempt is kept in the repository because it
motivated the harder mixture check (results/brackets/mixture/summary.md), not because
its own result says much on its own.

## Setup

Same design as the original bracketing run (results/brackets/): W1 eval split, gate
enabled, FreCoS eviction, cache_size_entries=1650, ttl_confidence=0.9,
cluster_count_k=10, three lambda_source values (global, learned, oracle) x 10 seeds
(0-9) = 30 runs. The only change: `generate_trace(..., half_life_shape=2.0)` draws each
cluster's true half-life from a Weibull distribution with the same mean scale as before
but shape 2 instead of the exponential's shape 1. `fit_staleness_table` still fits an
exponential (the only model this project's fitter implements), so it is now fitting the
wrong family by construction. `oracle_lambdas_for_seed` still reconstructs
1/half_life_scale, the true mean rate, since that is the best a constant-hazard oracle
table can encode; the Weibull's shape parameter has no equivalent slot in this project's
staleness table.

results.csv has exactly 30 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly.

## Bootstrap method

Same as the original bracketing run: percentile bootstrap over the 10 per-seed values in
each lambda_source group, 10,000 resamples with replacement (n=10 each), median of each
resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Mann-Whitney U

Same hand-rolled implementation as the other bracket runs (scipy not available in this
sandbox): ranks with average-rank tie handling, U = R1 - n1(n1+1)/2, normal approximation
for the p-value with the standard tie correction to the variance term.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median n_hits | median n_stale_hits_served |
|---|---|---|---|---|
| global | 0.0646 | (0.0153, 0.1266) | 132.5 | 8.0 |
| learned | 0.0000 | (0.0000, 0.0039) | 122.5 | 0.0 |
| oracle | 0.0000 | (0.0000, 0.0039) | 122.5 | 0.0 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 0.0, p ~ 0.00009 (significant, learned lower)
- learned vs oracle: U = 50.0, p ~ 1.0 (both exactly zero for essentially every seed)

## Why this run under-tests the misspecification question

A Weibull with shape 2 concentrates its mass more tightly around the mean than an
exponential with the same mean does (lower coefficient of variation), so fewer entries
in this run ever survive long enough to become stale in the first place -- the median
n_stale_hits_served for both learned and oracle is exactly 0 across seeds. With so few
stale-eligible hits to measure, stale_hit_rate floors at zero for both estimators and the
comparison has nothing left to distinguish MLE-recovery quality from oracle-recovery
quality. The learned-vs-global separation still holds (both estimators correctly avoid
serving the (rare) stale entries global fails to catch), but the learned-vs-oracle
question this misspecification check was meant to probe is not actually exercised here.
See results/brackets/mixture/summary.md for the adversarial case that does exercise it.
