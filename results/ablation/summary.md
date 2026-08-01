# Ablation: gate and eviction

## Setup

W1 eval split, 5 rows x 5 seeds = 25 runs, same trace generation as the bracketing
experiment: `generate_trace(n_tenants=5, n_clusters=10, n_queries=3000, seed=seed)`,
five distinct traces (one per seed), cache_size_entries=412, ttl_confidence=0.9,
cluster_count_k=10. Reduced-scale rerun with the generator text fix (see
results/brackets/summary.md for the root cause and fix); n_queries=3000 and 5 seeds,
not the pre-fix rerun's 12000 and 10.

cluster_ari (median ~0.42 across all rows) confirms the same fixed-clustering-quality
finding as the bracketing experiment.

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

results.csv has 25 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly (now including n_useful_hits and useful_hit_rate).

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each row: 10,000 resamples with
replacement (n=5 each), median of each resample, 95% CI from the 2.5th and 97.5th
percentiles. stdlib random, seeded 12345.

## Results

| Row | median stale_hit_rate | 95% CI | median hit_rate | median false_hit_rate | median cost_saved_usd |
|---|---|---|---|---|---|
| 1 LRU | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 1.90 |
| 2 LFU | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 1.90 |
| 3 BF-substitute | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 1.90 |
| 4 gate+LFU | 0.0677 | (0.0505, 0.0874) | 0.3360 | 0.9111 | 1.84 |
| 5 gate+FreCoS | 0.0677 | (0.0505, 0.0874) | 0.3360 | 0.9111 | 1.84 |

Rows 1-3 are byte-identical seed by seed, and rows 4-5 are byte-identical seed by seed.
Both are traced to real, distinct causes, not left as an unexplained coincidence:

**Rows 1-3 (gate off):** with the real semantic index's high hit rate at this
configuration, only 178-210 misses occur out of 1890 scored queries per run, well
under the 412-entry cache budget. The cache never fills, so eviction never runs at
all -- LRU, LFU, and the BF-substitute all tie because none of them is ever called to
select a victim, not because they agree on one. results/cost_aware_eviction/summary.md
confirms this directly by rerunning this exact gate-off configuration at a cache size
small enough to force real eviction pressure and finds real differences between the
three policies there.

**Rows 4-5 (gate on):** genuinely tie on every metric because FreCoS's decay term
contributes nothing measurable once the gate is active (see Interaction check below) --
this matches every prior version of this ablation and is unrelated to cache sizing,
since misses here (1165-1338 per run) comfortably exceed the 412-entry budget and
eviction does run.

## Interaction check: does the gate carry most of the improvement?

Isolating the two effects:

- Gate alone: row 4 vs row 2, stale_hit_rate 0.0677 vs 0.5464, delta -0.479.
- FreCoS's value function on top of the gate: row 5 vs row 4, delta 0.0000 (identical).

Mann-Whitney U, row 2 (floor) vs row 4 (gate+LFU), analysis/stats.py: U_a=25.0,
p ~ 0.0090, r ~ 1.00 (perfect separation, gate strictly lower stale-hit-rate on every
seed). The gate accounts for the entire measurable stale-hit-rate improvement in this
ablation; FreCoS's decay term adds nothing detectable on top of it, consistent with
every prior version of this ablation and with the design's own framing of the decay
term as a soft prior rather than the primary staleness-prevention mechanism.

## Design decisions made here

- Trace scale and cache size reused verbatim from the bracketing experiment (3000
  queries, 412 entries); verified via an in-code assertion on seed 0's trace.
- lambda_source is recorded as "learned" for gate-on rows and "none" for gate-off
  rows, matching the field's stated meaning rather than a placeholder value.
- Config.eviction_policy for row 3 is recorded as "BF_SUBSTITUTE" to make the
  substitution visible in the CSV itself without reading this file.
