# A8 bracketing: global vs learned vs oracle lambda

## Verdict

Mixed, and worth flagging to the human rather than silently rounding it to a clean pass.

Gate 3 asks two things: does learned lambda land strictly between global and oracle on
stale_hit_rate, and are the confidence intervals for learned and global non-overlapping.

The second half passes cleanly: learned's 95% CI is (0.0242, 0.0604) and global's is
(0.0851, 0.2143) -- no overlap, and Mann-Whitney U on learned vs global gives p ~ 0.0005.
Global is significantly worse.

The first half does not hold in the literal "strictly between" sense. Learned's median
stale_hit_rate is 0.0350 and oracle's is also 0.0350 -- in 8 of 10 seeds the two runs
produce byte-identical rows, and Mann-Whitney U on learned vs oracle gives p ~ 0.94, no
detectable difference. Learned isn't sitting in the middle of the bracket, it is sitting
at the oracle end of it. Global is the outlier, not the midpoint anchor.

This is not the failure mode the design doc worried about (learned collapsing onto
global). It is closer to the opposite: with this trace size, every cluster has 550-650
calibration observations, far above the fitter's n_obs >= 30 fallback threshold, so the
per-cluster MLE essentially recovers the true generator lambda and learned mode is
statistically indistinguishable from oracle mode. Flagging this for the human: the
literal Gate 3 checkbox ("strictly between") reads as failed, but the substantive claim
downstream experiments care about -- that per-cluster fitting beats a single pooled rate
-- is strongly supported. Whether that counts as a pass probably depends on whether Gate
3's intent was "learned works and is distinguishable from the naive baseline" (yes) or
"learned sits at a visibly intermediate point between the two brackets" (no, at this
calibration sample size). Recommend not treating this as the design doc's anticipated
negative-result trigger for a full characterization pivot (design sec 5.5), but a lighter
follow-up in A9/A10 checking whether the learned/oracle gap opens up at smaller
calibration sample sizes or under injected drift would be a reasonable thing to note as
a limitation.

## Setup

W1 eval split, gate enabled, FreCoS eviction, cache_size_entries = 1650, ttl_confidence =
0.9, cluster_count_k = 10. Three lambda_source values (global, learned, oracle) x 10
seeds (0-9) = 30 runs. results.csv has exactly 30 rows plus header, columns match
benchmarks.harness.CSV_COLUMNS exactly.

Ten distinct traces were generated, one per seed, rather than one trace replayed ten
times. The pipeline has no randomness of its own once a trace is fixed (eviction and the
gate are deterministic given metadata), so replaying a single trace ten times would give
ten byte-identical rows per lambda_source and nothing to bootstrap over. A fresh trace
per seed is what makes the seed axis in the plan mean anything.

n_queries = 12000 per trace (n_tenants=5, n_clusters=10), which yields exactly 6600
distinct answer_ids regardless of seed (4200 canonical + 2400 longtail; paraphrase and
repeat rows reuse existing answer_ids, so they don't add distinct ones). Cache size 1650
entries is 25% of that, inside the 20-30% range this card asks for as a placeholder
mid-point ahead of the real cache-size sweep in A10.

oracle_lambdas were reconstructed per seed by calling np.random.default_rng(seed) then
cluster_params(n_clusters, rng) -- the exact same first two lines generate_trace itself
runs before drawing anything else -- rather than inferring lambda from the trace's own
valid_until - t durations. The trace does not label which rows came from which
cluster_params draw in a way that would let you separate "true half-life" noise from
"sampled outcome" noise, so reconstructing the generator's own draw with an identical
seeded RNG call is the exact reproduction, not an approximation.

Known limitation carried over from the harness: it uses an exact-text-match index, no
semantic embedding index exists yet in this project, so paraphrase rows in the trace
never hit -- only literal repeats of a canonical query text do. Hit counts across all 30
runs are in the 116-165 range out of roughly 12,600 scored queries per run, well below
what a real semantic cache would show. This caps the sample of hits stale_hit_rate is
computed over and widens the CIs; it does not change the direction of the global vs
learned/oracle comparison, since the exact-match limitation applies identically to all
three lambda_source conditions.

## Bootstrap method

Simple percentile bootstrap over the 10 per-seed values in each lambda_source group:
10,000 resamples with replacement (n=10 each), median taken of each resample, and the
95% CI read off the 2.5th and 97.5th percentiles of the resulting distribution of
medians. Implemented with Python's stdlib random module, seeded (12345) for
reproducibility.

## Mann-Whitney U

scipy is not installed in this environment (environment.yml does not list it, and pip
installs are blocked by the sandbox's externally-managed-environment guard), so the U
statistic and its two-sided p-value were implemented directly: ranks with average-rank
tie handling, U = R1 - n1(n1+1)/2, normal approximation for the p-value with the standard
tie correction to the variance term. About 20 lines, no dependency added.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | 95% CI |
|---|---|---|---|---|
| global | 0.1436 | (0.0851, 0.2143) | 0.4480 | (0.3439, 0.5354) |
| learned | 0.0350 | (0.0242, 0.0604) | 0.4485 | (0.3440, 0.5367) |
| oracle | 0.0350 | (0.0284, 0.0639) | 0.4485 | (0.3440, 0.5367) |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 4.0, p ~ 0.00051 (significant, learned lower)
- learned vs oracle: U = 49.0, p ~ 0.9396 (not significant, indistinguishable)

cost_saved_usd is nearly identical across all three lambda_source values because
cost_saved only counts non-stale hits, and with the exact-match index the entries that
hit at all are overwhelmingly the same small set of frequently-repeated canonical
queries regardless of which gate threshold rejected the intervening stale copies -- the
gate changes which repeats get served versus regenerated, not which queries hit in the
first place. lambda_source therefore mostly redistributes hits between "served fresh"
and "served stale" rather than changing the hit set itself, which is why the headline
signal is entirely in stale_hit_rate and not in cost_saved_usd.
