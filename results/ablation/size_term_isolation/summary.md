# Size-term isolation: FreCoS with and without /size_bytes under tight cache pressure

## Verdict

Indistinguishable. At 330 entries -- 5% of this trace's 6600-answer_id working set, the
tightest point available at this scale -- FreCoS with and without the size term produce
statistically indistinguishable stale_hit_rate and hit_rate (Mann-Whitney p ~ 0.97 and
p ~ 0.31 respectively). The tight budget does raise eviction pressure, but that pressure
does not make the size term's contribution visible.

**Provenance.** This run is recorded at a 12000-query trace scale (6600 answer_ids) that
no command in this repo now regenerates; every other experiment behind the report runs at
3000 queries with a 1650-answer_id working set. It is kept as the only direct measurement
of the size term, and every number in it should be read at its own scale.

This is expected given how the eviction policy is actually invoked: this project runs
under an entry-count budget (evict one entry when the count exceeds
`cache_size_entries`), not a byte budget. Dividing `value()` by `size_bytes` only changes
the ranking among candidates competing for the same freed slot; it does not change how
much budget is freed by evicting any given entry, because evicting a 10-byte entry and a
10,000-byte entry both free exactly one slot. The term can shift *which* entry gets
evicted, but there is no economic mechanism here that rewards evicting large entries
specifically, so any effect on stale_hit_rate or hit_rate is second-order at best, which
is what the table below measures.

## Setup

`generate_trace(n_tenants=5, n_clusters=10, n_queries=12000, seed=seed)`, ten distinct
traces (seeds 0-9). Gate on (TTLGate, learned, ttl_confidence=0.9), FreCoS eviction,
cache_size_entries=330 -- 5% of this trace's working set, chosen because that is where
eviction happens most often and any size-driven ranking effect has the most opportunities
to matter.

Two rows: FreCoS with the size term (`row5_gate_frecos_smallcache`) and FreCoS with
`no_size=True` (`row6_gate_frecos_nosize_smallcache`). 20 rows in results.csv (2 rows x
10 seeds), columns match benchmarks.harness.CSV_COLUMNS.

## Bootstrap method

Same as the other ablation and sweep summaries: percentile bootstrap over the 10
per-seed values in each row, 10,000 resamples with replacement (n=10), median of each
resample, 95% CI from the 2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Results

The `cost_saved_usd` column below sums regeneration cost over all hits, not over useful
hits only as elsewhere in this repo (see results/cost_aware_eviction/summary.md), so it is
not comparable with the cost columns in the other summaries. The conclusion above rests on
stale_hit_rate and hit_rate, which are defined identically here and everywhere else.

| Row | median stale_hit_rate | 95% CI | median hit_rate | 95% CI | median cost_saved_usd | 95% CI |
|---|---|---|---|---|---|---|
| row5 (with size) | 0.0209 | (0.0103, 0.0283) | 0.0130 | (0.0122, 0.0134) | 0.3495 | (0.2754, 0.4483) |
| row6 (no size) | 0.0210 | (0.0106, 0.0350) | 0.0135 | (0.0123, 0.0140) | 0.4094 | (0.3077, 0.4732) |

Mann-Whitney U:

- stale_hit_rate: U = 50.5, p ~ 0.9698 (not significant, indistinguishable)
- hit_rate: U = 36.5, p ~ 0.3064 (not significant)

## Scope of the null result

The null result holds at the tightest budget this trace scale offers, 5% of the working
set, where eviction runs most often. Read together with the arithmetic argument above --
that an entry-count budget gives `/size_bytes` no mechanism to act through, however much
eviction pressure there is -- it says the size term is structurally uninformative under
this budgeting scheme, not that a size term never matters. Under a byte budget, where
freeing a large entry frees proportionally more of the budget, the term would have a
mechanism; measuring that needs a byte-budgeted harness, which this project does not have.
FreCoS's value function therefore carries no size term (gptcache_ext/eviction/frecos.py),
and the five-row ablation has no size-normalization row.
