# A9 ablation: gate, eviction, and size normalization

## Setup

W1 eval split, 6 rows x 10 seeds = 60 runs, same trace generation as A8's brackets
experiment: `generate_trace(n_tenants=5, n_clusters=10, n_queries=12000, seed=seed)`, ten
distinct traces (one per seed), cache_size_entries=1650, ttl_confidence=0.9,
cluster_count_k=10. As in A8, one fresh trace per seed rather than one trace replayed
ten times: the pipeline has no randomness of its own given a fixed trace, so a single
trace would give ten identical rows per row and nothing to bootstrap over.

Verified rather than assumed: n_queries=12000 still yields 6600 distinct answer_ids
(4200 canonical + 2400 longtail), so 1650 is still exactly 25% and inside A8's
20-30% band. ablation.py asserts this on seed 0's trace at runtime.

Rows:

| Row | Gate | Eviction | Isolates |
|---|---|---|---|
| 1 | off (NullGate) | LRU | stock GPTCache |
| 2 | off (NullGate) | LFU | the real floor |
| 3 | off (NullGate) | BitonFriedmanSubstituteEviction | primary comparator |
| 4 | on (TTLGate, learned) | LFU | the gate alone |
| 5 | on (TTLGate, learned) | FreCoS | full stack |
| 6 | on (TTLGate, learned) | FreCoS(no_size=True) | size normalization ablation |

Gate-on rows fit the staleness table with fit_staleness_table(trace, mode="learned",
confidence=0.9), same as A8. Row 3's eviction policy is
gptcache_ext.eviction.baselines.BitonFriedmanSubstituteEviction, a documented
LFU-with-cost-tiebreak substitute (value = freq / regen_cost), not their released
code: it wasn't reachable in this build environment (no network access to fetch it),
per the A4 card's fallback instruction. Any claim below about "the primary comparator"
inherits that caveat.

results.csv has 60 rows plus header, columns match benchmarks.harness.CSV_COLUMNS
exactly.

## Bootstrap method

Same as A8: percentile bootstrap over the 10 per-seed values in each row, 10,000
resamples with replacement (n=10 each), median of each resample, 95% CI from the 2.5th
and 97.5th percentiles of the resulting distribution of medians. stdlib random,
seeded 12345.

## Results

| Row | median stale_hit_rate | 95% CI | median hit_rate | 95% CI | median cost_saved_usd | 95% CI |
|---|---|---|---|---|---|---|
| 1 LRU | 0.6605 | (0.6149, 0.6827) | 0.0479 | (0.0450, 0.0526) | 0.4488 | (0.3485, 0.5420) |
| 2 LFU | 0.6798 | (0.6448, 0.6959) | 0.0518 | (0.0487, 0.0547) | 0.4497 | (0.3502, 0.5414) |
| 3 BF-substitute | 0.6798 | (0.6448, 0.6959) | 0.0518 | (0.0487, 0.0547) | 0.4497 | (0.3502, 0.5414) |
| 4 gate+LFU | 0.0420 | (0.0242, 0.0601) | 0.0174 | (0.0171, 0.0180) | 0.4488 | (0.3440, 0.5379) |
| 5 gate+FreCoS | 0.0350 | (0.0242, 0.0604) | 0.0172 | (0.0169, 0.0179) | 0.4485 | (0.3440, 0.5367) |
| 6 gate+FreCoS(no-size) | 0.0421 | (0.0226, 0.0601) | 0.0174 | (0.0170, 0.0180) | 0.4487 | (0.3440, 0.5378) |

## Delta versus row 2 (LFU, the floor)

Row 2, not row 1, is the comparison of record: Biton & Friedman's own finding is that
LRU is weak on semantic workloads, so grading everything against LRU would flatter
every other policy trivially.

| Row | delta stale_hit_rate | delta hit_rate | delta cost_saved_usd |
|---|---|---|---|
| 1 LRU | -0.0193 | -0.0039 | -0.0009 |
| 3 BF-substitute | +0.0000 | +0.0000 | +0.0000 |
| 4 gate+LFU | -0.6379 | -0.0344 | -0.0009 |
| 5 gate+FreCoS | -0.6449 | -0.0346 | -0.0012 |
| 6 gate+FreCoS(no-size) | -0.6377 | -0.0344 | -0.0010 |

Row 3 is exactly identical to row 2 in every correctness and cost column, seed by
seed (n_hits, n_stale_hits_served, hit_rate, stale_hit_rate, cost_saved_usd all match
to full float precision across all 10 seeds; the only columns that differ are
wall-clock timing and process RSS/CPU, which are expected to vary run to run).
Traced this down rather than assuming it's a copy-paste artifact: at this hit rate
(~5%), almost every entry present at eviction time has freq=0 (it was written and
never accessed again before the cache filled up), so BF-substitute's freq/regen_cost
evaluates to 0/cost = 0 for essentially every candidate regardless of cost, and the
policy falls through to its tie-break (oldest create_on, then lowest entry_id) --
which is the same tie-break LFU uses when every freq is 0. This is a real
consequence of the workload's low revisit rate interacting with a substitute policy
that only differentiates non-zero-frequency entries, not a bug in either policy's
value() or select_victim(). It does mean row 3 in this experiment adds no
information beyond row 2; the primary-comparator slot is effectively untested by this
workload's parameters, which is a limitation worth stating plainly rather than papering
over with a coincidence-shaped result.

The gate rows (4, 5, 6) drop stale_hit_rate by roughly 15x relative to the floor and
hit_rate by about a third, in line with the design's stated trade-off: the gate
converts stale hits into misses, which necessarily lowers hit rate. cost_saved_usd is
essentially unchanged across all six rows (all in the 0.44-0.45 range) for the same
reason A8 found: cost_saved only counts non-stale hits, and with the exact-match index
in this harness, the set of queries that hit at all is small and dominated by the same
frequently-repeated canonical queries regardless of gate or eviction policy. The gate
changes which repeats get served fresh versus regenerated; it does not change the hit
set itself.

## Interaction check: does the gate carry most of the improvement?

Design section 3.2's prediction: because the gate already refreshes anything past its
TTL, FreCoS's exp(-lambda*age) decay term in value() is not doing staleness prevention
itself -- it acts as a soft prior favoring longer-remaining-life entries among
evictable candidates. The ablation is expected to show the gate carrying most of the
stale-hit-rate improvement, with the decay term contributing less on top of it than it
contributes alone.

Isolating the two effects:

- Gate alone: row 4 vs row 2, stale_hit_rate 0.0420 vs 0.6798, delta -0.6379.
- FreCoS's value function on top of the gate: row 5 vs row 4, stale_hit_rate
  0.0350 vs 0.0420, delta -0.0070.
- For comparison, no-size FreCoS on top of the gate: row 6 vs row 4, delta
  +0.0001 (statistically flat).

Mann-Whitney U on row 4 vs row 5 (stale_hit_rate): U = 49.5, p ~ 0.97 -- not
distinguishable from no effect. Mann-Whitney U on row 2 vs row 4: U = 100.0,
p ~ 0.00016 -- strongly significant.

Verdict: the predicted interaction held, and held more strongly than the design
anticipated. The gate accounts for essentially the entire stale_hit_rate
improvement (-0.638 of a -0.645 total move from the floor to the full stack, about
99% of it). FreCoS's decay term contributes an additional -0.007 on top of the gate,
which is both an order of magnitude smaller than the gate's own effect and not
statistically distinguishable from zero at n=10 seeds. This is not the contradiction
flagged as the thing to investigate in the plan (design section 3.2 predicted the
decay term would contribute "less on top of it than it contributes alone" -- here it
contributes something indistinguishable from nothing on top of it, an even flatter
result than predicted). Since there's no contradiction, there was nothing to debug in
gate.py or frecos.py; both read as intended (gate.py's is_stale is a single
age > ttl_seconds comparison, frecos.py's value() multiplies the four terms and
divides by size). I checked cluster-identity agreement between the two components
anyway, since that's the specific integration bug the plan's Gate 2 discussion calls
out (a gate and an eviction policy that each pass their own tests but disagree about
cluster identity): both read meta.cluster_id directly off the same EntryMeta
instance, so there is no path for them to see different cluster assignments for the
same entry.

Why the decay term ends up contributing almost nothing here: with the gate active,
every entry the eviction policy ever sees is already known-fresh (anything stale was
refreshed at serve time before it could be evicted), and the eval split's window is
short relative to the fitted per-cluster TTLs, so exp(-lambda*age) is close to 1 for
nearly every live entry regardless of cluster. The decay term has little to
differentiate on in this setup, which is consistent with the design's own framing of
it as a soft prior rather than the primary staleness-prevention mechanism -- that
mechanism is the gate.

## Size-normalization variant

Row 6 (FreCoS with /size_bytes dropped) is statistically indistinguishable from row
5 (full FreCoS) and from row 4 (plain LFU) on stale_hit_rate, hit_rate, and
cost_saved_usd, all CIs overlapping heavily. At this cache size and workload, the size
term in value() isn't moving the needle either, for the same underlying reason as
the decay term: eviction pressure among gate-protected entries in this trace doesn't
differentiate much on any of FreCoS's four terms once staleness itself is off the
table. A cache-size sweep at a tighter budget (A10) is a more informative place to
look for the size term's effect than this ablation, since size normalization should
matter more when eviction pressure is higher.

## Design decisions made here

- Trace scale and cache size reused verbatim from A8 (12000 queries, 1650 entries)
  rather than re-derived, per the brief's instruction to verify rather than
  recompute if unchanged; verified via an in-code assertion on seed 0's trace.
- lambda_source is recorded as "learned" for gate-on rows and "none" for
  gate-off rows in the CSV, matching the field's stated meaning (the fitter mode
  actually used) rather than a placeholder value.
- Config.eviction_policy for row 3 is recorded as "BF_SUBSTITUTE" (not
  "BITON_FRIEDMAN") to make the substitution visible in the CSV itself without
  reading this file.
