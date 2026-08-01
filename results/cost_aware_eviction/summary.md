# Cost-aware eviction: a fair test of FreCoS's cost term

## Verdict

The generator text fix (see results/brackets/summary.md) does not change this
experiment's qualitative finding, and matches the report's existing framing
(the Phase 5 fix noted in CHANGES.md): with the gate off and real eviction pressure
forced by a small cache, LRU maximizes cost_saved_usd (median 1.60) *and* has the
lowest stale_hit_rate of the three (0.063) -- lower than both FreCoS (cost_saved 1.22,
stale_hit_rate 0.42) and LFU (cost_saved 0.70, stale_hit_rate 0.53). Recency of access
happens to track recency of write on this trace, so LRU gets a freshness benefit for
free with no staleness model at all; FreCoS does not beat LRU on either metric here.
FreCoS does beat LFU on cost_saved_usd with a large effect (p ~ 0.076, r ~ 0.68 -- not
significant at n=5, though the direction and magnitude match the pre-fix rerun's
significant result at n=10) and beats LRU decisively on stale_hit_rate (p ~ 0.009,
r ~ 1.00) -- but that comparison is against LRU, not evidence of an advantage; FreCoS
having a *lower* stale-hit-rate than LRU here would be the win, and the data shows the
opposite.

## Setup

W1 eval split, gate disabled (NullGate), three eviction policies (FreCoS, LFU, LRU) x
5 seeds each, n_queries=3000 (reduced-scale rerun, see brackets.py's docstring).
cache_size_entries=25, not the main ablation's 412: scaled down proportionally
(100 * 3000/12000 in the pre-fix version) from the value the original full-scale run
measured as comfortably forcing real eviction pressure; confirmed empirically here too
(1348-1435 misses out of 1890 scored queries per run, comfortably exceeding the
25-entry budget).

Real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters) and
benchmarks.semantic_index.SemanticIndex (0.8 threshold) are used, same as every other
experiment in this rerun; FreCoS still needs a staleness table for its decay term even
with the gate off, fit with mode="learned" (never consulted by NullGate).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each row: 10,000 resamples with
replacement (n=5), median of each resample, 95% CI from the 2.5th/97.5th percentiles.
Python stdlib random, seeded 12345.

## Results

| Row | median cost_saved_usd | 95% CI | median stale_hit_rate | median hit_rate |
|---|---|---|---|---|
| FreCoS | 1.22 | (0.86, 2.21) | 0.4205 | 0.2566 |
| LFU | 0.70 | (0.54, 1.46) | 0.5259 | 0.2190 |
| LRU | 1.60 | (1.11, 2.62) | 0.0629 | 0.2587 |

Mann-Whitney U (analysis/stats.py):

- FreCoS vs LFU, cost_saved_usd: U_a=21.0, p ~ 0.076, r ~ 0.68 (not significant at n=5, FreCoS higher, large effect)
- FreCoS vs LRU, cost_saved_usd: U_a=7.0, p ~ 0.251, r ~ -0.44 (not significant, LRU higher, medium effect)
- LFU vs LRU, cost_saved_usd: U_a=1.0, p ~ 0.016, r ~ -0.92 (significant, LRU higher)
- FreCoS vs LRU, stale_hit_rate: U_a=25.0, p ~ 0.009, r ~ 1.00 (significant, perfect separation; FreCoS *higher* i.e. worse than LRU here)

## Reading the trade-off

LRU wins on raw cost_saved_usd because it evicts the least-recently-accessed entry
regardless of cost or staleness, which happens to keep frequently-regenerated (costly)
entries in cache longer whenever recency and cost are correlated in this trace. LRU
also has the *lowest* stale_hit_rate of the three here (0.063 versus 0.421 for FreCoS
and 0.526 for LFU): with the gate off, LRU has no mechanism at all to avoid serving
stale entries, but its eviction choices happen to remove them anyway, since recency of
access correlates with recency of write on this trace. FreCoS sits between LFU and LRU
on cost_saved_usd while beating LFU: it is not purely cost-maximizing like LRU turns
out to be here, and it does meaningfully outperform the pure-frequency LFU floor on
cost, the trade-off its value function (freq x cost x freshness-decay) is designed to
strike -- but it does not beat LRU on either metric tested here, which the report
should state plainly rather than framing as a FreCoS win. At n=5 seeds the
FreCoS-vs-LFU cost_saved_usd comparison is directionally consistent with, but not
independently significant from, the pre-fix rerun's n=10 result (which was
significant, p ~ 0.0009); this is a power limitation of the reduced seed count, not a
change in the underlying effect.
