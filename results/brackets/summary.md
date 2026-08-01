# Bracketing: global vs learned vs oracle lambda

## Verdict

Rerun with the generator text fix (workloads/w1_synthetic/generator.py, see
CHANGES.md): canonical query text now carries a distinct topic phrase per cluster and
a distinct aspect/qualifier phrase per answer, replacing the old two-digit-suffix
template that a real embedder could not use to recover cluster identity at all. Median
cluster_ari rises from 0.036 (pre-fix) to 0.42 across this rerun's 15 runs -- a real,
substantial cluster signal, not a perfect one. With that signal in place, the original
bracketing pattern is restored: learned (median stale_hit_rate 0.068) sits significantly
below global (0.091, p ~ 0.028, r ~ -0.84) and significantly above oracle (0.048,
p ~ 0.016, r ~ 0.92) -- per-cluster fitting beats pooling, and does not fully close the
gap to a perfect oracle, which is the expected, defensible shape for this result.

This reverses the prior remediation pass's finding ("learned tracks global, not
oracle") -- but that finding was correct for the workload it was tested against; the
workload itself was the bug, not the clustering or calibration code. Direct inspection
of same-cluster embeddings (see "Root cause of the generator fix" below) shows the
fix's remaining imperfection: same-cluster, different-aspect canonical queries (e.g. two distinct
"Renaissance art" questions on different aspects) score 0.7-0.8 cosine similarity, close
to the SemanticIndex's 0.8 match threshold, which is why false_hit_rate is still high
(median ~0.91) though down from the pre-fix ~0.97. This is a more realistic failure
mode than the old cross-cluster-conflation bug -- same-topic paraphrase-adjacent
queries genuinely can look similar to a general-purpose embedder -- but it means
false_hit_rate remains a first-order caveat on every number below, not a solved problem.

## Setup

W1 eval split, gate enabled, FreCoS eviction, cache_size_entries=412 (25% of the
1650-answer_id working set at this scale), ttl_confidence=0.9, cluster_count_k=10.
n_queries=3000 (not the pre-fix rerun's 12000) and 5 seeds (not 10): reduced scale for
this rerun, since the generator fix invalidated every previously committed
results.csv and rerunning at the original scale was judged not worth the ~9-hour,
almost-entirely-embedding cost for validating a fix whose thesis-level conclusion does
not depend on trace size (see CHANGES.md). Three lambda_source values (global,
learned, oracle) x 5 seeds (0-4) = 15 runs. results.csv has exactly 15 rows plus
header, columns match benchmarks.harness.CSV_COLUMNS exactly (now including
n_useful_hits and useful_hit_rate, added alongside this rerun -- see
results/sweeps/ttl_confidence/summary.md for why).

Each row's cluster_id comes from gptcache_ext.staleness.assign_real_clusters: every
distinct query text in the trace is embedded once (GPTCache's default ONNX model,
cached to disk by text hash), k-means is fit on the calibration split's embeddings, and
every row (calibration and eval) is assigned to its nearest centroid. The generator's
true cluster label is kept as true_cluster_id for the ARI figure only. For the oracle
arm specifically, cluster_id is restored to true_cluster_id after the ARI is computed:
oracle_lambdas_for_seed's table is keyed by the generator's true cluster, and under
real, imperfect clustering a learned cluster id no longer maps 1:1 to a true cluster,
so oracle's fit and serve path must keep using true cluster identity to retain its
original meaning (the ceiling a perfect clusterer would achieve).

Lookup is benchmarks.semantic_index.SemanticIndex: brute-force cosine similarity
against every cached entry's embedding, GPTCache's default 0.8 threshold.

Five distinct traces were generated, one per seed, rather than one trace replayed five
times, for the same reason as always: the pipeline has no randomness of its own once a
trace is fixed, so a repeated trace would give nothing to bootstrap over.

## Root cause of the generator fix (for context)

Pre-fix, W1's canonical query template was `"What is the current status of topic
{cluster_id}-{answer_id}?"` -- identical across every cluster except two embedded
integers. A general-purpose sentence embedder cannot use numeric substitution inside an
otherwise-fixed template to recover cluster identity; cross-cluster template pairs
scored 0.6-0.9 cosine similarity, often higher than genuine same-cluster paraphrase
pairs, and cluster_ari was 0.02-0.06 (random-assignment level) across every experiment
in the pre-fix rerun.

The fix (workloads/w1_synthetic/generator.py) replaces this with per-cluster topic
phrases (CLUSTER_TOPICS, 51 distinct real-world subjects) combined with per-answer
aspect and qualifier phrases (ANSWER_ASPECTS x ANSWER_QUALIFIERS, 750 combinations per
cluster) drawn by each canonical answer's position within its own cluster -- not a
global answer_id, since a global-index-based stride can alias back onto the same
vocabulary slot far sooner than the vocabulary actually repeats (see the generator's
`local_index` comment). tests/test_w1.py now asserts cluster_ari > 0.5 on a
3000-query, seed-0 trace as a regression guard.

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each lambda_source group: 10,000
resamples with replacement (n=5 each), median of each resample, 95% CI from the
2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Mann-Whitney U and effect size

analysis/stats.py (hand-rolled: scipy not available in this sandbox), rank-biserial
correlation r = 2*U_a/(n1*n2) - 1 as effect size -- not r = |z|/sqrt(n1+n2), which an
earlier version of this project mislabeled "rank-biserial." The two formulas disagree
materially, and the z-based one discards the sign of the effect; see
analysis/stats.py's module docstring.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median false_hit_rate | median cost_saved_usd | median cluster_ari |
|---|---|---|---|---|---|
| global | 0.0911 | (0.0847, 0.1553) | 0.898 | 1.99 | 0.419 |
| learned | 0.0677 | (0.0505, 0.0874) | 0.911 | 1.84 | 0.419 |
| oracle | 0.0484 | (0.0420, 0.0529) | 0.914 | 1.92 | 0.419 |

(cluster_ari is identical across lambda_source rows within a seed, since clustering is
fit once per trace before lambda_source-specific fitting; the median above is over all
15 rows.)

Mann-Whitney U, stale_hit_rate:

- learned vs global: U_a=2.0, p ~ 0.0283, r ~ -0.84 (significant, large effect, learned lower/better)
- learned vs oracle: U_a=24.0, p ~ 0.0163, r ~ 0.92 (significant, large effect, learned worse than oracle)
- global vs oracle: U_a=25.0, p ~ 0.0090, r ~ 1.00 (significant, perfect separation)

## Takeaway for the report

With cluster identity actually recoverable from the query text (median cluster_ari
0.42, versus 0.036 pre-fix), per-cluster fitting beats pooling with a large,
significant effect, and sits significantly closer to oracle without fully reaching it
-- the shape the original pre-remediation report claimed, now backed by a workload a
real embedder can actually separate. false_hit_rate remains high (median ~0.91): the
fix solved cross-cluster conflation but not same-cluster, different-aspect similarity,
which a 0.8 cosine threshold still often crosses. Every number here should be read
alongside that caveat, same as the pre-fix version of this report already insisted on.
