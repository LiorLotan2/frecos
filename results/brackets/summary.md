# Bracketing: global vs learned vs oracle lambda

## Verdict

Rerun with real embedder-based clustering and a semantic index (previously this ran
with oracle-perfect cluster identity and exact-match lookup). The finding reverses
compared to the earlier oracle-cluster run: learned is no longer distinguishable from
global (p ~ 0.94), and is now significantly worse than oracle (p ~ 0.0005, r ~ 0.78).
Under oracle cluster identity, learned tracked oracle almost exactly and clearly beat
global; under real clustering, learned tracks global almost exactly and clearly loses
to oracle. The clustering step, not the per-cluster MLE fit, is now the bottleneck.

Root cause, verified directly rather than assumed: the adjusted Rand index between the
generator's true cluster labels and the k-means-on-embeddings assignment is 0.036-0.062
across the 30 runs -- barely above what a random assignment would produce. Direct
inspection of the embeddings explains why: the W1 generator's canonical query template
("What is the current status of topic {cluster}-{answer}?") is identical across every
cluster except two embedded numbers, and a general-purpose sentence embedder scores
cross-cluster template pairs at 0.6-0.9 cosine similarity, often higher than genuine
paraphrase pairs. The text simply does not encode cluster identity in a way a real
embedder can recover; this is a property of the workload's text design, not a bug in
the k-means implementation (gptcache_ext/staleness/clusters.py) or the embedder wiring
(gptcache_ext/staleness/embedder.py).

false_hit_rate is no longer identically zero, another effect of the same underlying
cause but on a different axis: the semantic index's 0.8 cosine threshold accepts the
same template-similarity that defeats clustering, so it also serves many false hits
(median false_hit_rate ~0.97 across all three lambda_source conditions -- see Results).
This was invisible under the old exact-match index, which structurally could not have a
false hit.

## Setup

W1 eval split, gate enabled, FreCoS eviction, cache_size_entries = 1650, ttl_confidence =
0.9, cluster_count_k = 10. Three lambda_source values (global, learned, oracle) x 10
seeds (0-9) = 30 runs. results.csv has exactly 30 rows plus header, columns match
benchmarks.harness.CSV_COLUMNS exactly (now including cluster_ari).

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

Lookup is now benchmarks.semantic_index.SemanticIndex: brute-force cosine similarity
against every cached entry's embedding, GPTCache's default 0.8 threshold, replacing the
prior exact-text-match index.

Ten distinct traces were generated, one per seed, rather than one trace replayed ten
times, for the same reason as always: the pipeline has no randomness of its own once a
trace is fixed, so a repeated trace would give nothing to bootstrap over.

n_queries = 12000 per trace (n_tenants=5, n_clusters=10), cache_size_entries=1650.

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each lambda_source group: 10,000
resamples with replacement (n=10 each), median of each resample, 95% CI from the
2.5th/97.5th percentiles. Python stdlib random, seeded 12345.

## Mann-Whitney U

Hand-rolled (scipy not available in this sandbox): ranks with average-rank tie
handling, U = R1 - n1(n1+1)/2, normal approximation for the p-value with the standard
tie correction to the variance term, rank-biserial r = |z|/sqrt(n1+n2) as effect size.

## Results

| lambda_source | median stale_hit_rate | 95% CI | median false_hit_rate | median cost_saved_usd | 95% CI | median cluster_ari |
|---|---|---|---|---|---|---|
| global | 0.0772 | (0.0571, 0.0973) | ~0.97 | 14.86 | (11.77, 17.47) | 0.036 |
| learned | 0.0707 | (0.0594, 0.0909) | ~0.97 | 14.95 | (11.66, 17.07) | 0.036 |
| oracle | 0.0416 | (0.0387, 0.0469) | ~0.97 | 15.51 | (12.03, 17.89) | 0.036 |

(cluster_ari is identical across lambda_source rows within a seed, since clustering is
fit once per trace before lambda_source-specific fitting; the median above is over all
30 rows.)

Mann-Whitney U, stale_hit_rate:

- learned vs global: U = 49.0, p ~ 0.940, r ~ 0.017 (not significant, indistinguishable)
- learned vs oracle: U = 96.0, p ~ 0.0005, r ~ 0.78 (significant, large effect, learned worse)
- global vs oracle: U = 98.0, p ~ 0.0003, r ~ 0.81 (significant, large effect)

cost_saved_usd is close across all three lambda_source values (14.86-15.51), a smaller
relative spread than stale_hit_rate's, for the same structural reason as before: it
counts non-stale hits only, and the semantic index's very high hit rate under all three
conditions means most of the movement between conditions shows up in which hits are
stale rather than in how many hits occur at all.

## Takeaway for the report

The report's original framing -- "learned recovers close to the oracle rate, beating
pooling by 4x" -- depended entirely on oracle-perfect cluster identity, which this
project never actually exercised in any reported number until this rerun. With real
clustering, that framing does not hold: learned performs like global, not like oracle.
The honest finding is that per-cluster fitting only pays off if cluster identity is
itself recoverable, and it is not recoverable from this workload's query text under a
real embedder. This needs to be the report's central limitation, not a footnote.
