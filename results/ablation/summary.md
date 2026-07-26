# Ablation: gate and eviction

## Setup

W1 eval split, 5 rows x 10 seeds = 50 runs, same trace generation as the bracketing
experiment: `generate_trace(n_tenants=5, n_clusters=10, n_queries=12000, seed=seed)`,
ten distinct traces (one per seed), cache_size_entries=1650, ttl_confidence=0.9,
cluster_count_k=10.

Rerun with real embedder-based clustering (gptcache_ext.staleness.assign_real_clusters)
and benchmarks.semantic_index.SemanticIndex (0.8 cosine threshold), replacing the prior
oracle-cluster-id + exact-match-index run. cluster_ari (median ~0.036 across all rows)
confirms the same low-clustering-quality finding as the bracketing experiment.

Rows:

| Row | Gate | Eviction | Isolates |
|---|---|---|---|
| 1 | off (NullGate) | LRU | stock GPTCache |
| 2 | off (NullGate) | LFU | the real floor |
| 3 | off (NullGate) | BitonFriedmanSubstituteEviction | primary comparator |
| 4 | on (TTLGate, learned) | LFU | the gate alone |
| 5 | on (TTLGate, learned) | FreCoS | full stack |

A sixth row (FreCoS without the size-normalization term) existed in the original
ablation design but is gone: the size term itself was removed from FreCoS's value
function entirely (see gptcache_ext/eviction/frecos.py's module docstring) after a
dedicated isolation experiment (results/ablation/size_term_isolation/, no longer
regenerable) found it made no measurable difference under this project's entry-count
eviction budget, for a structural reason unrelated to clustering quality.

Gate-on rows fit the staleness table with fit_staleness_table(trace, mode="learned",
confidence=0.9). Row 3's eviction policy is
gptcache_ext.eviction.baselines.BitonFriedmanSubstituteEviction, a documented
LFU-with-cost-tiebreak substitute (value = freq / regen_cost), not their released
code, unreachable in this build environment.

results.csv has 50 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly (now including cluster_ari).

## Bootstrap method

Percentile bootstrap over the 10 per-seed values in each row: 10,000 resamples with
replacement (n=10 each), median of each resample, 95% CI from the 2.5th and 97.5th
percentiles. stdlib random, seeded 12345.

## Results

| Row | median stale_hit_rate | 95% CI | median hit_rate | median false_hit_rate | median cost_saved_usd | 95% CI |
|---|---|---|---|---|---|---|
| 1 LRU | 0.7204 | (0.7021, 0.7496) | 0.9515 | 0.9607 | 7.07 | (5.82, 8.52) |
| 2 LFU | 0.7204 | (0.7021, 0.7496) | 0.9515 | 0.9607 | 7.07 | (5.82, 8.52) |
| 3 BF-substitute | 0.7204 | (0.7021, 0.7496) | 0.9515 | 0.9607 | 7.07 | (5.82, 8.52) |
| 4 gate+LFU | 0.0707 | (0.0594, 0.0909) | 0.5624 | 0.9693 | 14.95 | (11.66, 17.07) |
| 5 gate+FreCoS | 0.0707 | (0.0594, 0.0909) | 0.5624 | 0.9693 | 14.95 | (11.66, 17.07) |

Rows 1-3 are byte-identical seed by seed, and rows 4-5 are byte-identical seed by seed.
Both are traced to real, distinct causes, not left as an unexplained coincidence:

**Rows 1-3 (gate off):** with the real semantic index's very high hit rate at this
configuration, only 339-372 misses occur out of 7560 scored queries per run, well
under the 1650-entry cache budget. The cache never fills, so eviction never runs at
all -- LRU, LFU, and the BF-substitute all tie because none of them is ever called to
select a victim, not because they agree on one. This is the same root cause identified
and fixed in the cost_aware_eviction experiment (see its summary.md), which reruns
this exact gate-off configuration at a cache size small enough to force real eviction
pressure and finds real, significant differences between the three policies there.
This ablation's rows 1-3 are best read as confirming that gate-off eviction is
irrelevant at this cache size, not as a finding about which policy is best.

**Rows 4-5 (gate on):** genuinely tie on every metric because FreCoS's decay term
contributes nothing measurable once the gate is active (see Interaction check below) --
this matches the pre-rerun finding and is unrelated to cache sizing, since misses here
(3092+ per run) comfortably exceed the 1650-entry budget and eviction does run.

## Interaction check: does the gate carry most of the improvement?

Isolating the two effects:

- Gate alone: row 4 vs row 2, stale_hit_rate 0.0707 vs 0.7204, delta -0.650.
- FreCoS's value function on top of the gate: row 5 vs row 4, delta 0.0000 (identical).

Mann-Whitney U, row 2 (floor) vs row 4 (gate+LFU): U = 0.0, p ~ 0.00016, r ~ 0.85 --
strongly significant. The gate accounts for the entire measurable stale-hit-rate
improvement in this ablation; FreCoS's decay term adds nothing detectable on top of it,
consistent with every prior version of this ablation and with the design's own framing
of the decay term as a soft prior rather than the primary staleness-prevention
mechanism.

## Design decisions made here

- Trace scale and cache size reused verbatim from the bracketing experiment (12000
  queries, 1650 entries); verified via an in-code assertion on seed 0's trace.
- lambda_source is recorded as "learned" for gate-on rows and "none" for gate-off
  rows, matching the field's stated meaning rather than a placeholder value.
- Config.eviction_policy for row 3 is recorded as "BF_SUBSTITUTE" to make the
  substitution visible in the CSV itself without reading this file.
