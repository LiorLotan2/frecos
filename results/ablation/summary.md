# Ablation: gate and eviction

## Setup

W1 eval split, 5 rows x 5 seeds = 25 runs, same trace generation as the bracketing
experiment: `generate_trace(n_tenants=5, n_clusters=10, n_queries=3000, seed=seed)`,
five distinct traces (one per seed), cache_size_entries=412, ttl_confidence=0.9,
cluster_count_k=10.

cluster_ari (median 0.42 across all rows) matches the bracketing experiment's clustering
quality, as expected from the shared trace generation.

Rows:

| Row | Gate | Eviction | Isolates |
|---|---|---|---|
| 1 | off (NullGate) | LRU | stock GPTCache |
| 2 | off (NullGate) | LFU | the real floor |
| 3 | off (NullGate) | BitonFriedmanSubstituteEviction | primary comparator |
| 4 | on (TTLGate, learned) | LFU | the gate alone |
| 5 | on (TTLGate, learned) | FreCoS | full stack |

There is no size-normalization row, because FreCoS's value function carries no size term
(see gptcache_ext/eviction/frecos.py's module docstring): eviction here runs under an
entry-count budget, which gives `/size_bytes` no mechanism to act through, and a
dedicated isolation experiment measured no difference from it
(results/ablation/size_term_isolation/, a historical artifact that no command in this
repo regenerates).

Gate-on rows fit the staleness table with fit_staleness_table(trace, mode="learned",
confidence=0.9). Row 3's eviction policy is
gptcache_ext.eviction.baselines.BitonFriedmanSubstituteEviction, a documented
LFU-with-cost-tiebreak substitute (value = freq * regen_cost), not their released
code, which this project never obtained.

results.csv has 25 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly, including n_useful_hits and useful_hit_rate.

## Bootstrap method

Percentile bootstrap over the 5 per-seed values in each row: 10,000 resamples with
replacement (n=5 each), median of each resample, 95% CI from the 2.5th and 97.5th
percentiles. stdlib random, seeded 12345.

## Results

| Row | median stale_hit_rate | 95% CI | median hit_rate | median false_hit_rate | median cost_saved_usd |
|---|---|---|---|---|---|
| 1 LRU | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 0.126 |
| 2 LFU | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 0.126 |
| 3 BF-substitute | 0.5464 | (0.4667, 0.5994) | 0.8942 | 0.9225 | 0.126 |
| 4 gate+LFU | 0.0677 | (0.0505, 0.0874) | 0.3360 | 0.9111 | 0.191 |
| 5 gate+FreCoS | 0.0677 | (0.0505, 0.0874) | 0.3360 | 0.9111 | 0.191 |

Rows 1-3 agree on every cache metric seed by seed, and so do rows 4-5 (the latency, CPU,
RSS and timestamp columns differ, as wall-clock measurements do between runs).
Both ties have one measured cause: eviction never fires anywhere in this ablation.

**Eviction never runs.** Instrumenting `select_victim` over all 25 runs records zero
calls and zero evictions in every one of the five rows. Against the 412-entry budget the
resident set peaks at 256-291 entries, so no row ever reaches the point where a victim
has to be chosen. Entries are keyed by query text (benchmarks.harness.ExactMatchIndex,
which benchmarks.semantic_index.SemanticIndex inherits), so a repeated miss on a text
already resident replaces that entry rather than adding one; occupancy is bounded by the
number of distinct texts that miss, not by the miss count, which is 178-210 scored misses
per run in rows 1-3 and 1165-1338 in rows 4-5 out of 1890 scored queries.

Every tie in the table above is therefore trivial rather than substantive. Rows 1-3
differ only in eviction policy, and none of LRU, LFU or the BF-substitute is ever called
to select a victim, so those three rows are one configuration executed three times. Rows
4-5 differ only in eviction policy in the same way, so FreCoS's value function is never
consulted there either. The five rows collapse to two distinct configurations, gate off
and gate on: **this ablation measures the gate alone.**

The eviction value function is exercised only by results/cost_aware_eviction/, at a
25-entry budget, where `select_victim` runs 1385-1586 times per run depending on arm and
seed and the cache sits pinned at 25/25. Every claim about FreCoS's cost and decay terms
rests on that experiment, not on this one.

## What this ablation isolates

- Gate alone: row 4 vs row 2, stale_hit_rate 0.0677 vs 0.5464, delta -0.479.
- FreCoS's value function on top of the gate: not measured here. Row 5 vs row 4 is a
  delta of exactly 0.0000 because eviction never fires, so the two rows run identical
  code paths. It is not evidence about the value function in either direction.

Mann-Whitney U, row 2 (floor) vs row 4 (gate+LFU), analysis/stats.py: U_a=25.0,
p ~ 0.0090, r ~ 1.00 (perfect separation, gate strictly lower stale-hit-rate on every
seed). This is designated primary comparison P2 in analysis/multiple_comparisons.py, so
it is reported uncorrected and holds at alpha = 0.05; `make multiple-comparisons` prints
it next to the Holm-corrected secondary family.

The gate accounts for the entire measurable stale-hit-rate improvement in this ablation,
and it is the only mechanism this ablation puts under test.

## Design decisions made here

- Trace scale and cache size reused verbatim from the bracketing experiment (3000
  queries, 412 entries); verified via an in-code assertion on seed 0's trace.
- lambda_source is recorded as "learned" for gate-on rows and "none" for gate-off
  rows, matching the field's stated meaning rather than a placeholder value.
- Config.eviction_policy for row 3 is recorded as "BF_SUBSTITUTE" to make the
  substitution visible in the CSV itself without reading this file.
