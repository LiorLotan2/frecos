# Bracketing follow-up: calibration at scarcer sample size

## Verdict

Still indistinguishable. The learned/oracle gap does not open up at this calibration
size. Mann-Whitney U on learned vs oracle gives p ~ 0.963, essentially the same
non-result as the original bracketing run's p ~ 0.94.

Learned continues to separate cleanly from global (p ~ 0.0015, and this time the medians
themselves are visibly different: global's stale_hit_rate median is 0.1742, learned's is
0.0000). But learned and oracle track each other almost exactly across all 10 seeds --
7 of the 10 seed pairs are byte-identical in stale_hit_rate, the same pattern the original
bracketing run saw.

This is a genuine negative result for the "scarcer calibration opens the gap" hypothesis,
not a bug. See below for why: the calibration sample did shrink by an order of magnitude,
but not the axis that matters for this comparison.

## Setup

Same design as the original bracketing run: W1 eval split, gate enabled, FreCoS eviction,
ttl_confidence = 0.9, cluster_count_k = 10, three lambda_source values (global, learned,
oracle) x 10 seeds (0-9) = 30 runs. results.csv has exactly 30 rows plus header, columns
match benchmarks.harness.CSV_COLUMNS exactly.

The only design change from the original bracketing run is n_queries: 1800 instead of
12000, with cache_size_entries scaled down to 248 (25% of the 990 distinct answer_ids
this trace size yields, same 20-30% range the original run used). Ten distinct traces,
one per seed, same rationale as before: the pipeline is deterministic given a trace, so a
fixed trace replayed ten times gives nothing to bootstrap over.

oracle_lambdas were reconstructed the same way as the original bracketing run:
np.random.default_rng(seed) then cluster_params(n_clusters, rng), true lambda per cluster
is 1/half_life_scale.

## Calibration observations per cluster

This is the number the whole follow-up hinges on. At n_queries=1800 the per-cluster
calibration counts (n_obs from fit_staleness_table's ClusterStaleness objects, mode
learned) come out at:

| seed | min n_obs | max n_obs |
|---|---|---|
| 0 | 46 | 60 |
| 1 | 50 | 61 |
| 2 | 48 | 68 |
| 3 | 41 | 62 |
| 4 | 43 | 70 |
| 5 | 43 | 69 |
| 6 | 41 | 71 |
| 7 | 42 | 71 |
| 8 | 45 | 71 |
| 9 | 34 | 64 |

Across all 10 seeds and 10 clusters, n_obs ranges from 34 to 71, roughly 40-70 in the
typical case. That is well above the fitter's n_obs >= 30 fallback floor (so clusters are
not degrading to the global rate trivially, which would prove nothing) and roughly an
order of magnitude below the original bracketing run's 550-650 per cluster. This is
squarely the target range the follow-up asked for.

## Why the gap still doesn't open

The exponential MLE's relative standard error scales as 1/sqrt(n_obs). At n_obs ~ 50 that
is roughly 14%, versus roughly 4% at the original run's n_obs ~ 600. So the per-cluster
lambda estimates genuinely are noisier here than in the original run -- that part worked
as intended.

What did not change is the number of eval-split hits available to actually detect that
noise. n_hits per run dropped from the original run's 116-165 range down to 8-34 here
(n_queries fell by 6.7x, and hit counts fell roughly proportionally since the harness's
exact-match index caps hits at repeated canonical-query text). With single-digit-to-thirties
hit counts, stale_hit_rate for a run is a ratio over a handful of events, and for most
seeds it swings straight to zero for both learned and oracle -- there just aren't enough
stale-eligible hits left in the eval split for a noisier lambda estimate to visibly cost
anything.

So shrinking n_queries loosened the calibration split's sample size as intended, but it
also shrank the eval split's hit count in lockstep, and it's the eval-side hit count that
determines whether the extra calibration noise ever surfaces in stale_hit_rate. Scarcer
calibration and scarcer eval evidence move together here because both come from the same
trace-size knob; separating them (e.g. holding eval hits roughly fixed while shrinking
only the calibration window) would be a different experiment than the one this follow-up
was asked to run.

## Bootstrap method

Same method as the original bracketing run: percentile bootstrap over the 10 per-seed
values in each lambda_source group, 10,000 resamples with replacement (n=10 each), median
of each resample, 95% CI from the 2.5th/97.5th percentiles of the resample medians.
Python stdlib random, seeded 12345.

## Mann-Whitney U

Same hand-rolled implementation as the original bracketing run (scipy still not available
in this sandbox): ranks with average-rank tie handling, U = R1 - n1(n1+1)/2, normal
approximation for the p-value with the standard tie correction to the variance term.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | 95% CI |
|---|---|---|---|---|
| global | 0.1742 | (0.1123, 0.2381) | 0.0667 | (0.0581, 0.0888) |
| learned | 0.0000 | (0.0000, 0.1290) | 0.0667 | (0.0552, 0.0957) |
| oracle | 0.0000 | (0.0000, 0.1290) | 0.0667 | (0.0552, 0.0957) |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 9.0, p ~ 0.00154 (significant, learned lower)
- learned vs oracle: U = 49.5, p ~ 0.9628 (not significant, indistinguishable)

For reference, the original bracketing run's numbers at n_queries=12000: learned vs
global p ~ 0.00051, learned vs oracle p ~ 0.9396. The learned-vs-global separation is if
anything a bit noisier here (wider CIs, smaller hit counts) but still clearly
significant. The learned-vs-oracle p-value is essentially unchanged.

cost_saved_usd is flat across all three conditions here for the same reason the original
bracketing run saw: it only counts non-stale hits, and lambda_source mostly redistributes
a small, mostly-fixed set of hits between "served fresh" and "served stale" rather than
changing which queries hit in the first place.

## Takeaway for the report

The negative result stands up under a second, differently-sized run: learned genuinely
recovers something close to the oracle lambda across a wide range of calibration sample
sizes for this generator (from ~600 obs/cluster down to ~50 obs/cluster), not just at the
large end the original bracketing run happened to pick. That is a stronger form of the
same substantive claim the original run's verdict made -- per-cluster fitting beats
pooling, and does so robustly -- even though it still does not produce the literal
"learned strictly between global and oracle" picture the original design was looking for.
Opening daylight between learned and oracle on this generator would likely need either a
much smaller n_obs (closer to or below the n_obs=30 fallback floor, which the follow-up
was explicitly asked not to target) or a workload where the per-cluster generating
process is less well-approximated by a single exponential, not just fewer queries.
