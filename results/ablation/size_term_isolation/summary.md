# Size-term isolation: FreCoS with and without /size_bytes under tight cache pressure

## Verdict

Still indistinguishable. Even at 330 entries (5% of the 6600-answer_id working set,
versus 1650 in the main ablation), FreCoS with and without the size term produce
statistically indistinguishable stale_hit_rate and hit_rate (Mann-Whitney p ~ 0.97 and
p ~ 0.31 respectively). Tightening the cache budget did increase eviction pressure
(hit_rate dropped from ~0.017 at 1650 entries to ~0.013 here), but that pressure did not
make the size term's contribution visible.

This is expected given how the eviction policy is actually invoked: this project runs
under an entry-count budget (evict one entry when the count exceeds
`cache_size_entries`), not a byte budget. Dividing `value()` by `size_bytes` only changes
the ranking among candidates competing for the same freed slot; it does not change how
much budget is freed by evicting any given entry, because evicting a 10-byte entry and a
10,000-byte entry both free exactly one slot. The term can shift *which* entry gets
evicted, but there is no economic mechanism here that rewards evicting large entries
specifically, so any effect on stale_hit_rate or hit_rate is expected to be second-order
at best -- consistent with what both the main ablation and this isolation run show.

## Setup

Same trace generation as the main ablation and the cache-size sweep:
`generate_trace(n_tenants=5, n_clusters=10, n_queries=12000, seed=seed)`, ten distinct
traces (seeds 0-9). Gate on (TTLGate, learned, ttl_confidence=0.9), FreCoS eviction,
cache_size_entries=330 -- the smallest point from the cache-size sweep, chosen because
that is where eviction happens most often and any size-driven ranking effect has the
most opportunities to matter.

Two rows: FreCoS with the size term (`row5_gate_frecos_smallcache`) and FreCoS with
`no_size=True` (`row6_gate_frecos_nosize_smallcache`). 20 rows in results.csv (2 rows x
10 seeds), columns match benchmarks.harness.CSV_COLUMNS.

## Bootstrap method

Same as the other ablation and sweep summaries: percentile bootstrap over the 10
per-seed values in each row, 10,000 resamples with replacement (n=10), median of each
resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Results

The `cost_saved_usd` column below predates the metric change that excludes false hits (see
results/cost_aware_eviction/summary.md), so it is not comparable with the cost columns in
the other summaries here. This run is not regenerable, and the conclusion above rests on
stale_hit_rate and hit_rate, neither of which the metric change touches.

| Row | median stale_hit_rate | 95% CI | median hit_rate | 95% CI | median cost_saved_usd | 95% CI |
|---|---|---|---|---|---|---|
| row5 (with size) | 0.0209 | (0.0103, 0.0283) | 0.0130 | (0.0122, 0.0134) | 0.3495 | (0.2754, 0.4483) |
| row6 (no size) | 0.0210 | (0.0106, 0.0350) | 0.0135 | (0.0123, 0.0140) | 0.4094 | (0.3077, 0.4732) |

Mann-Whitney U:

- stale_hit_rate: U = 50.5, p ~ 0.9698 (not significant, indistinguishable)
- hit_rate: U = 36.5, p ~ 0.3064 (not significant)

## Reading this together with the main ablation's row 6

The main ablation (results/ablation/summary.md) found the same null result at
cache_size_entries=1650 and speculated that a tighter budget might surface a size-term
effect. This isolation run tightens the budget by 5x and the result does not change.
Combined with the arithmetic argument above -- that an entry-count budget gives
`/size_bytes` no mechanism to act through regardless of how much eviction pressure there
is -- the null result here should be read as confirming that this ablation row is
structurally uninformative under the current budgeting scheme, not as evidence that a
size term never matters. See the report's Discussion for the design decision made in
response to this finding.
