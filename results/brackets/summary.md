# Bracketing: global vs learned vs oracle lambda

## Verdict

Median cluster_ari is 0.42 across this experiment's 15 runs: a real, substantial cluster
signal, not a perfect one. Under that signal, learned (median stale_hit_rate 0.068) sits
below global (0.091, U_a=2.0, p ~ 0.028, r ~ -0.84) and above oracle (0.048, U_a=24.0,
p ~ 0.016, r ~ 0.92). Per-cluster fitting beats pooling, and does not close the gap to a
perfect oracle.

learned vs global is designated primary comparison P1 in
analysis/multiple_comparisons.py, reported uncorrected, and holds at alpha = 0.05.
learned vs oracle is secondary comparison S1: its Holm-adjusted p over the ten-member
secondary family is 0.114, so it does not hold at alpha = 0.05.
`make multiple-comparisons` prints both.

false_hit_rate is high (median 0.91) and is a first-order caveat on every number below.
Direct inspection of same-cluster embeddings locates it: same-cluster, different-aspect
canonical queries (two distinct "Renaissance art" questions on different aspects, for
instance) score 0.7-0.8 cosine similarity, close to the SemanticIndex's 0.8 match
threshold, so same-topic queries about different aspects can match each other.

## Setup

W1 eval split, gate enabled, FreCoS eviction, cache_size_entries=412 (25% of the
1650-answer_id working set at this scale), ttl_confidence=0.9, cluster_count_k=10.
n_queries=3000 and 5 seeds, a deliberate statistical-power cost: a full-scale run at
12000 queries and 10 seeds is on the order of a 9-hour, almost entirely embedding-bound
job on this machine, and the conclusion this experiment supports does not depend on trace
size. Three lambda_source values (global, learned, oracle) x 5 seeds (0-4) = 15 runs.
results.csv has exactly 15 rows plus header, columns match
benchmarks.harness.CSV_COLUMNS exactly, including n_useful_hits and useful_hit_rate (see
results/sweeps/ttl_confidence/summary.md for what useful_hit_rate counts).

Each row's cluster_id comes from gptcache_ext.staleness.assign_real_clusters: every
distinct query text in the trace is embedded once (GPTCache's default ONNX model,
cached to disk by text hash), k-means is fit on the calibration split's embeddings, and
every row (calibration and eval) is assigned to its nearest centroid. The generator's
true cluster label is kept as true_cluster_id for the ARI figure only. For the oracle
arm specifically, cluster_id is restored to true_cluster_id after the ARI is computed:
oracle_lambdas_for_seed's table is keyed by the generator's true cluster, and under
real, imperfect clustering a learned cluster id does not map 1:1 to a true cluster, so
oracle's fit and serve path must keep using true cluster identity to retain its meaning
(the ceiling a perfect clusterer would achieve).

Lookup is benchmarks.semantic_index.SemanticIndex: brute-force cosine similarity
against every cached entry's embedding, GPTCache's default 0.8 threshold.

Five distinct traces were generated, one per seed, rather than one trace replayed five
times: the pipeline has no randomness of its own once a trace is fixed, so a repeated
trace would give nothing to bootstrap over.

## Canonical query text and cluster separability

Cluster identity has to be recoverable from query text alone for this experiment to mean
anything, since clustering is fit from embeddings of that text.
workloads/w1_synthetic/generator.py builds canonical query text from per-cluster topic
phrases (CLUSTER_TOPICS, 51 distinct real-world subjects) crossed with per-answer aspect
and qualifier phrases (ANSWER_ASPECTS x ANSWER_QUALIFIERS, 750 combinations per cluster),
keyed by each canonical answer's position within its own cluster rather than by a global
answer_id: a global-index stride aliases back onto the same vocabulary slot far sooner
than the vocabulary itself repeats (see the generator's `local_index` comment).
tests/test_w1.py asserts cluster_ari > 0.5 on a 3000-query, seed-0 trace as a regression
guard.

A template that varies only in embedded integers does not meet that requirement: a
general-purpose sentence embedder cannot use numeric substitution inside an otherwise
fixed template to recover cluster identity, and cross-cluster pairs of such templates
score 0.6-0.9 cosine similarity, often above genuine same-cluster paraphrase pairs, which
puts cluster_ari at random-assignment level (0.02-0.06).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each lambda_source group: 10,000
resamples with replacement (n=5 each), median of each resample, 95% CI from the
2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Mann-Whitney U and effect size

analysis/stats.py (hand-rolled: scipy not available in this sandbox), rank-biserial
correlation r = 2*U_a/(n1*n2) - 1 as effect size, not r = |z|/sqrt(n1+n2), which is a
z-based rank correlation that disagrees with rank-biserial materially and discards the
sign of the effect; see analysis/stats.py's module docstring.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median false_hit_rate | median cost_saved_usd | median cluster_ari |
|---|---|---|---|---|---|
| global | 0.0911 | (0.0847, 0.1553) | 0.898 | 0.188 | 0.419 |
| learned | 0.0677 | (0.0505, 0.0874) | 0.911 | 0.191 | 0.419 |
| oracle | 0.0484 | (0.0420, 0.0529) | 0.914 | 0.187 | 0.419 |

(cluster_ari is identical across lambda_source rows within a seed, since clustering is
fit once per trace before lambda_source-specific fitting; the median above is over all
15 rows.)

Mann-Whitney U, stale_hit_rate. p is raw; the Holm-adjusted p of every comparison the
report quotes is printed by `make multiple-comparisons`.

- learned vs global: U_a=2.0, p ~ 0.0283, r ~ -0.84 (large effect, learned lower/better; primary P1, exempt from correction, holds)
- learned vs oracle: U_a=24.0, p ~ 0.0163, r ~ 0.92 (large effect, learned worse than oracle; secondary S1, Holm-adjusted p 0.114, does not hold)
- global vs oracle: U_a=25.0, p ~ 0.0090, r ~ 1.00 (perfect separation; not among the comparisons the report quotes, so not in the corrected family)

## Takeaway for the report

With cluster identity recoverable from the query text (median cluster_ari 0.42),
per-cluster fitting beats pooling with a large effect on the primary comparison, and sits
between pooling and oracle without reaching oracle. false_hit_rate is high (median 0.91):
same-cluster, different-aspect similarity crosses the 0.8 cosine threshold often, so
every number here should be read alongside that caveat.
