# Cost-aware eviction: a fair test of FreCoS's cost term

## Verdict

Negative result. With the gate off and real eviction pressure forced by a small cache,
FreCoS's cost term does not separate from the pure-frequency LFU floor on cost_saved_usd
(median 0.138 vs 0.120, U_a=13.0, p ~ 0.917, r ~ 0.04), and LRU leads on both metrics:
highest cost_saved_usd (median 0.213) and by far the lowest stale_hit_rate (0.092, versus
0.421 for FreCoS and 0.526 for LFU). Recency of access tracks recency of write on this
trace, so LRU gets a freshness benefit for free with no staleness model at all. FreCoS
beats neither comparator on either metric here.

Two metric definitions matter for reading the numbers. `last_access` advances on a hit,
so the LRU row is real LRU and not insertion order. And `cost_saved_usd` sums regeneration
cost over useful hits only (neither stale nor false), which is why absolute cost values
are roughly a tenth of what an all-hits sum would give at this workload's ~0.87
false-hit-rate: hits that returned a stale or wrong answer saved no backend call the
caller would have accepted.

This is the only experiment in the project that exercises FreCoS's eviction value
function. At the 25-entry budget, `select_victim` runs 1385-1586 times per run depending
on arm and seed and the cache sits pinned at 25/25. The five-row ablation
(results/ablation/summary.md) runs at a 412-entry budget that the resident set never
reaches, so eviction never fires there at all.

## Setup

W1 eval split, gate disabled (NullGate), three eviction policies (FreCoS, LFU, LRU) x
5 seeds each, n_queries=3000 (the scale every experiment behind the report runs at, see
brackets.py's docstring). cache_size_entries=25, not the main ablation's 412: 25 entries is
the budget that forces real eviction pressure at this trace scale, re-derived empirically
and confirmed here (1325-1515 misses out of 1890 scored queries per run, far exceeding the
25-entry budget).

Real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters) and
benchmarks.semantic_index.SemanticIndex (0.8 threshold) are used, same as every other
experiment behind the report; FreCoS still needs a staleness table for its decay term even
with the gate off, fit with mode="learned" (never consulted by NullGate).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each row: 10,000 resamples with
replacement (n=5), median of each resample, 95% CI from the 2.5th/97.5th percentiles.
Python stdlib random, seeded 12345.

## Results

| Row | median cost_saved_usd | 95% CI | median stale_hit_rate | median hit_rate | median useful_hit_rate |
|---|---|---|---|---|---|
| FreCoS | 0.138 | (0.084, 0.234) | 0.4205 | 0.2566 | 0.0769 |
| LFU | 0.120 | (0.075, 0.216) | 0.5259 | 0.2190 | 0.0870 |
| LRU | 0.213 | (0.133, 0.365) | 0.0920 | 0.2799 | 0.1228 |

Mann-Whitney U (analysis/stats.py). p is raw; `make multiple-comparisons` prints the
Holm-adjusted p of every comparison the report quotes, and no secondary comparison in that
family holds at alpha = 0.05, including the two perfect separations below.

- FreCoS vs LFU, cost_saved_usd: U_a=13.0, p ~ 0.917, r ~ 0.04 (no effect; secondary S6, adjusted p 0.917)
- FreCoS vs LRU, cost_saved_usd: U_a=5.0, p ~ 0.117, r ~ -0.60 (not significant at n=5, LRU higher, large effect; secondary S7, adjusted p 0.352)
- FreCoS vs LRU, stale_hit_rate: U_a=25.0, p ~ 0.009, r ~ 1.00 (perfect separation, FreCoS *higher* i.e. worse than LRU here; secondary S8, adjusted p 0.090)
- LRU vs LFU, stale_hit_rate: U_a=0.0, p ~ 0.009, r ~ -1.00 (perfect separation, LRU lower; secondary S9, adjusted p 0.090)
- LFU vs LRU, cost_saved_usd: U_a=4.0, p ~ 0.076, r ~ -0.68 (not significant, LRU higher, large effect; not among the comparisons the report quotes)
- FreCoS vs LRU, useful_hit_rate: U_a=0.0, p ~ 0.009, r ~ -1.00 (perfect separation, LRU higher; not among the comparisons the report quotes)

## Reading the trade-off

Under a 25-entry budget with no gate active, the LRU resident set is close to the 25 most
recently touched entries, and since every miss inserts a freshly created entry, an entry
that survives under LRU is usually one created recently. Evicting the least recently used
entry is therefore very nearly evicting the entry most likely to have expired, which is
where LRU's 0.092 stale_hit_rate comes from with no staleness mechanism at all. Its
cost_saved_usd advantage follows from the same place: cost saved counts useful hits only,
and useful_hit_rate orders exactly as cost does (0.123 LRU, 0.087 LFU, 0.077 FreCoS).

FreCoS's value function (freq x cost x freshness-decay) is designed to strike a
cost-versus-freshness trade-off, and at this cache size on this trace it strikes neither:
indistinguishable from LFU on cost, well behind LRU on both metrics. The failure is about
the trace as much as the value function, since creation age and access recency line up
closely enough here that recency alone approximates freshness. Separating them requires a
workload where those two orderings come apart, which W1 does not provide.
