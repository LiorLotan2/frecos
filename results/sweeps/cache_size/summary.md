# A10 cache-size sweep

## Setup

W1, gate enabled, FreCoS eviction, lambda_source=learned. Fixed defaults while sweeping
cache size: ttl_confidence=0.9, cluster_count_k=10. n_queries=12000 with n_tenants=5,
n_clusters=10, which (as in A8) yields exactly 6600 distinct answer_ids per trace
regardless of seed. Five cache-size points at 5%, 15%, 30%, 50%, 80% of that working set:
330, 990, 1980, 3300, 5280 entries, following the plan's own suggested spacing exactly.

Ten distinct traces per point (seeds 0-9), not one trace replayed ten times, for the same
reason as A8/A9: the pipeline has no randomness of its own given a fixed trace, so a
repeated trace would give ten identical rows and nothing to bootstrap over.

50 rows in results.csv (5 points x 10 seeds), matching benchmarks.harness.CSV_COLUMNS.

## Bootstrap method

Same as A8: simple percentile bootstrap over the 10 per-seed values at each cache-size
point. 10,000 resamples with replacement (n=10), median of each resample, 95% CI read off
the 2.5th/97.5th percentiles of the resulting distribution. Python stdlib random, seeded
12345.

## Results

| cache_size_entries | median hit_rate | 95% CI | median stale_hit_rate | 95% CI |
|---|---|---|---|---|
| 330  | 0.0130 | (0.0122, 0.0134) | 0.0209 | (0.0103, 0.0283) |
| 990  | 0.0169 | (0.0163, 0.0173) | 0.0327 | (0.0211, 0.0545) |
| 1980 | 0.0174 | (0.0171, 0.0180) | 0.0420 | (0.0242, 0.0601) |
| 3300 | 0.0174 | (0.0171, 0.0180) | 0.0420 | (0.0242, 0.0601) |
| 5280 | 0.0174 | (0.0171, 0.0180) | 0.0420 | (0.0242, 0.0601) |

## Effect direction

hit_rate is monotone increasing in cache size, but flattens completely after 1980
entries: the per-seed n_hits at 1980, 3300, and 5280 are identical query-by-query, meaning
once the cache is large enough it never has to evict anything a query would have hit
again during the eval window, so growing it further has zero effect on which queries hit.
stale_hit_rate follows the same pattern (increasing, then flat), which follows directly
since it is a ratio computed over the same fixed hit set once hit_rate stops moving.

Neither metric is non-monotone; both are increasing-then-flat over this range, which is
qualitatively different from monotone-increasing-forever. It means the working set as
generated does not need a cache anywhere close to 80% of 6600 entries to realize almost
all of its achievable hit rate at this trace size.

## Knee

Marginal hit-rate gain per additional cache entry, i.e. slope = delta(median hit_rate) /
delta(cache_size_entries) between consecutive points:

| step | delta hit_rate | delta entries | slope |
|---|---|---|---|
| 330 -> 990   | 0.003968 | 660  | 6.01e-6 |
| 990 -> 1980  | 0.000463 | 990  | 4.68e-7 |
| 1980 -> 3300 | 0.0      | 1320 | 0.0     |
| 3300 -> 5280 | 0.0      | 1980 | 0.0     |

Criterion: the knee is the first point after which slope drops by more than an order of
magnitude relative to the previous step. Slope drops by ~13x going from the 330->990 step
to the 990->1980 step, and by a further ~1000x (to exactly zero) going into the 1980->3300
step. The largest relative drop happens right after 1980, so **1980 entries (30% of the
working set) is the knee** -- the last point where an additional 990-entry increment still
bought any measurable hit-rate improvement (0.000463) at all. Beyond it, tripling the
cache to 5280 buys nothing.

This should be read together with the exact-match index limitation noted in A8/A9's
summaries: with only literal repeats able to hit (no semantic index wired in yet), the hit
set is small and saturates fast. A semantic index would likely push the knee to a larger
cache size, since paraphrase and repeat traffic that currently misses would start
contending for cache slots.
