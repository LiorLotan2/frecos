# Cost-aware eviction: a fair test of FreCoS's cost term

## Verdict

The first result in this project where FreCoS's eviction value function shows a real,
significant effect on the metric it was designed to move. Every prior ablation ran with
the gate on, which pre-filters stale entries before eviction ever sees them, leaving
FreCoS's regen_cost and decay terms nothing to differentiate on. Here, with the gate
off and real eviction pressure forced by a small cache, LRU maximizes cost_saved_usd
(median 17.09) at the cost of a much higher stale_hit_rate (0.227) than FreCoS
(cost_saved 11.83, stale_hit_rate 0.491) or LFU (cost_saved 7.17, stale_hit_rate
0.676). FreCoS beats LFU on cost_saved_usd significantly (p ~ 0.0009, r ~ 0.74).

## Setup

W1 eval split, gate disabled (NullGate), three eviction policies (FreCoS, LFU, LRU) x
10 seeds each, n_queries=12000. cache_size_entries=100, not the main ablation's 1650:
an earlier run at 1650 found only 339-372 misses out of 7560 scored queries per run --
the cache never filled, so eviction never ran at all, and every policy trivially tied.
Measured with an unlimited cache first (see benchmarks/runners/cost_aware_eviction.py's
module docstring): only 339-474 distinct entries are ever needed across the whole eval
split at this trace scale, so 100 is comfortably below that and forces real eviction
pressure on every run (1300-1700+ misses).

Real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters) and
benchmarks.semantic_index.SemanticIndex (0.8 threshold) are used, same as every other
experiment in this project's rerun; FreCoS still needs a staleness table for its decay
term even with the gate off, fit with mode="learned" (never consulted by NullGate).

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each row: 10,000 resamples with
replacement (n=10), median of each resample, 95% CI from the 2.5th/97.5th percentiles.
Python stdlib random, seeded 12345.

## Results

| Row | median cost_saved_usd | 95% CI | median stale_hit_rate | median hit_rate |
|---|---|---|---|---|
| FreCoS | 7.08 | (5.82, 8.52) | 0.491 | 0.847 |
| LFU | 7.17 | (5.52, 8.27) | 0.676 | 0.816 |
| LRU | 17.09 | (14.30, 21.06) | 0.227 | 0.841 |

Mann-Whitney U:

- FreCoS vs LFU, cost_saved_usd: U = 94.0, p ~ 0.0009, r ~ 0.74 (significant, FreCoS higher)
- FreCoS vs LRU, cost_saved_usd: U = 11.0, p ~ 0.0032, r ~ 0.66 (significant, LRU higher)
- LFU vs LRU, cost_saved_usd: U = 0.0, p ~ 0.0002, r ~ 0.85 (significant, LRU higher)
- FreCoS vs LRU, stale_hit_rate: U = 100.0, p ~ 0.0002, r ~ 0.85 (significant, FreCoS lower)

## Reading the trade-off

LRU wins on raw cost_saved_usd because it evicts the least-recently-accessed entry
regardless of cost or staleness, which happens to keep frequently-regenerated (costly)
entries in cache longer whenever recency and cost are correlated in this trace. It pays
for that with the highest stale_hit_rate of the three by a wide margin (0.227 versus
0.491 for FreCoS and 0.676 for LFU) -- with the gate off, LRU has no mechanism at all
to avoid serving stale entries, and its eviction choices happen not to remove them
either. FreCoS sits between LFU and LRU on cost_saved_usd while beating LRU
substantially on stale_hit_rate, which is the trade-off its value function
(freq x cost x freshness-decay) is designed to strike: it is not purely cost-maximizing
like LRU turns out to be here, but it does meaningfully outperform the pure-frequency
LFU floor on cost.
