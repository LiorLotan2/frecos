# Bracketing follow-up: calibration at scarcer sample size

## Verdict

Rerun with real embedder-based clustering and a semantic index. The pattern matches the
main bracketing rerun exactly: learned tracks global (p ~ 0.65, indistinguishable), not
oracle (p ~ 0.0003, r ~ 0.81). Clustering quality, not calibration sample size, remains
the bottleneck: cluster_ari here is ~0.055, essentially the same as the main run's
~0.036, since both traces use the identical query-text template that a real embedder
cannot separate by cluster (see results/brackets/summary.md for the direct evidence).
The original question this follow-up asked -- does the learned/oracle gap open up with
scarcer calibration data -- is moot under real clustering: the gap that matters here is
learned-vs-oracle, and it is wide regardless of calibration sample size, because the
clustering step upstream of calibration is where the information is lost.

## Setup

Same design as the main bracketing experiment: W1 eval split, gate enabled, FreCoS
eviction, ttl_confidence = 0.9, cluster_count_k = 10, three lambda_source values x 10
seeds, but n_queries=1800 instead of 12000 and cache_size_entries=248 (25% of this
trace's smaller distinct-answer_id count), the scarcer-calibration design this follow-up
was built for. Real clustering (gptcache_ext.staleness.assign_real_clusters) and
benchmarks.semantic_index.SemanticIndex (0.8 threshold) replace the prior oracle-cluster
+ exact-match setup, same as every other experiment in this rerun.

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each lambda_source group, 10,000
resamples, median of each resample, 95% CI from the 2.5th/97.5th percentiles. Python
stdlib random, seeded 12345.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median cost_saved_usd | 95% CI | median n_hits | median false_hit_rate |
|---|---|---|---|---|---|---|
| global | 0.0729 | (0.0651, 0.0841) | 2.07 | (1.61, 2.43) | 584.0 | 0.961 |
| learned | 0.0709 | (0.0608, 0.0864) | 2.11 | (1.59, 2.44) | 582.5 | 0.961 |
| oracle | 0.0324 | (0.0195, 0.0514) | 2.16 | (1.59, 2.46) | 569.5 | 0.966 |

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 44.0, p ~ 0.650, r ~ 0.10 (not significant)
- learned vs oracle: U = 98.0, p ~ 0.0003, r ~ 0.81 (significant, large effect)
- global vs oracle: U = 100.0, p ~ 0.0002, r ~ 0.85 (significant, large effect)

## Takeaway for the report

This follow-up was originally designed to test whether scarcer calibration data widens
the learned/oracle gap that the well-specified bracketing run couldn't detect. Under
real clustering, that question is answered by a different mechanism than intended: the
gap is already wide at every calibration sample size, because clustering -- which
happens before calibration in the pipeline -- fails to recover cluster identity from
this workload's query text regardless of how much data feeds the per-cluster MLE
downstream. Scarcer calibration would only matter if clustering itself were already
working.
