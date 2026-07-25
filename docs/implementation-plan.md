# FreCoS — Implementation Plan

Companion to `frecos-design.md`. This is the execution contract: it decomposes the design
into agent-sized units with frozen interfaces, disjoint file ownership, and mechanical
acceptance criteria.

**Read order for anyone executing:** §1 (protocol) → §2 (contracts, frozen) → your agent
card in §4 → §5 (gates).

---

## 1. Execution protocol

### 1.1 Agent cards

Each unit in §4 is an **agent card** with six mandatory fields: mandate, tasks, files owned,
acceptance criteria, forbidden paths, and size. A card is the entire brief. If a card is
ambiguous, the agent stops and asks — a wrong guess about an interface propagates to every
downstream agent.

### 1.2 Rules binding every agent

1. **Own only your files.** Touching a forbidden path is an automatic reject, even if the
   change looks correct.
2. **Contracts in §2 are frozen.** No agent modifies `gptcache_ext/contracts.py` or the
   schemas in §2.3–2.4. Change requests go to the human, who re-freezes and re-dispatches
   affected cards.
3. **Tests ship with code.** A card is incomplete without its tests green in CI.
4. **No agent declares its own completion.** Acceptance criteria are run by the integrator
   (§5); results are read, not trusted.
5. **Determinism is a hard requirement.** Every randomness path takes an explicit seed. No
   unseeded `random()`, no dict-iteration-order dependence, no wall-clock in logic — inject
   `now`.
6. **Never use `last_access` for age.** The highest-risk silent bug in the design.
   `EntryMeta.last_access` exists only for parity with upstream and for LRU baselines. Any
   use of it in a staleness or freshness computation fails review. Three independent checks
   guard this (A2 invariant, A3 unit test, A4 unit test) because it invalidates every
   staleness number without breaking anything visibly.

### 1.3 Branching

`main` protected and green only. One branch per card: `phase-N/<agent-id>-<slug>`. Merge
order within a phase follows card order. The integrator merges, never the agents.

---

## 2. Frozen contracts

These let five agents build in parallel without seeing each other's code. A1 writes them
verbatim; nobody edits them afterwards.

### 2.1 `gptcache_ext/contracts.py`

```python
"""Frozen interface contracts. Do not modify without re-freezing the plan."""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

class Decision(str, Enum):
    HIT            = "hit"
    MISS_ABSENT    = "miss_absent"      # index returned no candidate
    MISS_THRESHOLD = "miss_threshold"   # candidate below similarity threshold
    MISS_STALE     = "miss_stale"       # candidate rejected by validity gate

@dataclass(frozen=True)
class EntryMeta:
    entry_id:    int
    cluster_id:  int
    answer_id:   int    # ground-truth answer identity of the cached response
    create_on:   float  # unix seconds; generation time. AGE IS COMPUTED FROM THIS.
    last_access: float  # unix seconds; LRU baselines only. NEVER used for age.
    valid_until: float  # ground truth, harness-only. Cache logic MUST NOT read this.
    freq:        float  # decayed access count
    regen_cost:  float  # USD: output_tokens * price_per_token, recorded at write
    size_bytes:  int

@dataclass(frozen=True)
class ClusterStaleness:
    cluster_id:  int
    lambda_:     float  # validity decay rate, units 1/second
    ttl_seconds: float  # derived from lambda_ at the configured confidence
    n_obs:       int    # observations backing the fit

class StalenessTable(Protocol):
    def get(self, cluster_id: int) -> ClusterStaleness:
        """Returns the global fallback for an unseen cluster_id. Never raises."""

class Gate(Protocol):
    def is_stale(self, meta: EntryMeta, now: float) -> bool: ...

class EvictionPolicy(Protocol):
    def value(self, meta: EntryMeta, now: float) -> float: ...
    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        """Returns victim entry_id. Deterministic: ties break on oldest create_on,
        then lowest entry_id."""
```

**`valid_until` is carried on `EntryMeta` for harness scoring only.** No gate, policy, or
pipeline code may read it — that would be reading the answer key. A2's invariant suite
greps the `gptcache_ext/` tree for `valid_until` outside `metadata.py` and fails the build
on a hit.

### 2.2 `gptcache_ext/pipeline.py` — the single serve-path seam

```python
def decide(query, index, threshold, gate, now) -> tuple[Decision, EntryMeta | None]:
    candidate = index.search(query)
    if candidate is None:                      return Decision.MISS_ABSENT, None
    if candidate.rank < threshold:             return Decision.MISS_THRESHOLD, None
    if gate.is_stale(candidate.meta, now):     return Decision.MISS_STALE, candidate.meta
    return Decision.HIT, candidate.meta
```

`NullGate.is_stale()` always returns `False`. With `NullGate` + LRU, the pipeline must be
decision-identical to stock GPTCache — asserted by `tests/test_stock_parity.py`.

### 2.3 Workload trace schema (JSONL, one object per query)

The interchange format between workload builders and everything downstream. **W1 and W2
both emit this**, which is what makes them substitutable in the harness.

```json
{"t": 1690000000.0, "query_id": 8123, "text": "...", "cluster_id": 3,
 "answer_id": 42, "valid_until": 1690086400.0, "regen_cost": 0.0012,
 "size_bytes": 840, "paraphrase_of": 17, "split": "calib"}
```

| Field | Meaning |
|---|---|
| `t` | Arrival time, unix seconds. Monotonic non-decreasing within a file |
| `answer_id` | Ground-truth answer identity. Two queries sharing `answer_id` *should* share a cached answer |
| `valid_until` | **Ground truth for staleness.** The answer generated at `t` stops being correct at `valid_until`. `inf` for never-stale |
| `paraphrase_of` | `query_id` of the canonical form, or `null`. Ground truth for false-hit measurement |
| `regen_cost`, `size_bytes` | What a miss costs and occupies |
| `split` | `"calib"` (first 30% by `t`) or `"eval"` (remaining 70%). Set by the generator, never recomputed downstream |

Scoring definitions, computed by the harness and never by the cache:
- **Stale hit:** a served `HIT` where `t_serve > entry.valid_until`.
- **False hit:** a served `HIT` where `entry.answer_id != query.answer_id`.

### 2.4 Results CSV schema

One row per (configuration × seed). Written by the harness, read by analysis. Column order
fixed.

```
run_id, workload, policy, gate_enabled, lambda_source, cache_size_entries,
cluster_count_k, ttl_confidence, seed, split,
n_queries, n_hits, n_misses, n_stale_hits_served, n_stale_hits_prevented, n_false_hits,
hit_rate, stale_hit_rate, false_hit_rate,
cost_saved_usd, cost_spent_usd,
latency_mean_ms, latency_p50_ms, latency_p95_ms, latency_p99_ms,
throughput_qps, overhead_mean_ms, peak_rss_mb, cpu_pct,
git_sha, timestamp
```

`lambda_source ∈ {none, global, learned, oracle}` — the bracketing analysis (A8) is a
groupby on this column, not a bespoke script. `stale_hit_rate = n_stale_hits_served /
n_hits`.

### 2.5 Simulation model — how a "miss" works

**No LLM is called at any point.** The harness is a trace replayer. This must be stated in
the report's Experimental Setup, because it is a validity limitation a grader will probe.

| Quantity | Source |
|---|---|
| Miss response content | Taken from the trace (`answer_id`); nothing is generated |
| Miss cost | `regen_cost` from the trace, added to `cost_spent_usd` |
| Miss latency | **Simulated:** drawn from a seeded distribution fitted to the Azure LLM Inference Trace, conditioned on `size_bytes`. Deterministic per (seed, query_id) |
| Hit latency | **Measured for real:** actual embed + index search + gate time on the test machine |
| Extension overhead | **Measured for real:** cluster lookup + gate check, timed separately |

So reported latency is a hybrid — real cache-side cost, simulated backend cost. This is the
right trade (it makes runs free, deterministic, and CI-able) but the report says so plainly
and reports `overhead_mean_ms` separately so the real measured component is visible on its
own.

**Warmup.** The cache starts empty. The first 10% of the evaluation split is warmup:
replayed to populate the cache, excluded from all metrics. `n_queries` counts scored queries
only.

**Embedder.** Pinned to GPTCache's default ONNX `paraphrase-albert-onnx`, CPU-only, version
recorded in `README.md`. Do not substitute — embeddings determine cluster assignment,
similarity ranks, and therefore every downstream number.

### 2.6 Repository layout — ownership map

```
frecos/
├── .github/workflows/ci.yml            A1
├── Dockerfile, environment.yml         A1
├── Makefile                            A1
├── README.md                           A1 (owns file; A7 replaces ONLY the
│                                           <!-- BENCHMARK:A7 --> block)
├── vendor/gptcache/                    A1 (pinned; read-only afterwards)
├── gptcache_ext/
│   ├── contracts.py                    A1  [FROZEN]
│   ├── pipeline.py, metadata.py, config.py   A2
│   ├── staleness/{clusters,fitter,gate}.py   A3
│   └── eviction/{frecos,baselines}.py        A4
├── workloads/w1_synthetic/             A5
├── workloads/w2_wikipedia/             A0 (spike) → A6
├── benchmarks/{harness,metrics}.py     A7
├── benchmarks/runners/{brackets,ablation,sweeps}.py   A8, A9, A10 (one file each)
├── tests/
│   ├── oracle/reference_cache.py, invariants.py,
│   │   test_stock_parity.py, test_pipeline.py        A2
│   ├── test_staleness.py               A3
│   ├── test_frecos.py                  A4
│   ├── test_w1.py                      A5
│   ├── test_w2.py                      A6
│   └── test_metrics.py                 A7
├── results/{brackets,ablation,sweeps}/ A8, A9, A10 (disjoint)
├── analysis/                           A11
└── docs/                               per-file, see cards
```

---

## 3. Dependency graph and sizing

```
A0 (W2 spike) ─────── GATE 1 ──────┐
                                    │
A1 ── A2 ─┬─ A3 (staleness) ────────┤
          ├─ A4 (eviction+baselines)┤
          ├─ A5 (W1)                ┼─ GATE 2 ─ A8 ─ GATE 3 ─┬─ A9  ─┐
          ├─ A6 (W2)*               ┤                         └─ A10 ─┼─ A11 ─ A12
          └─ A7 (harness)  ─────────┘                                 │
A13 (baseline 1-pager) ── independent after A1 ───────────────────────┘
                                                    * only if GATE 1 green
```

| Card | Size | Phase | Blocking? |
|---|---|---|---|
| A0 W2 spike | S (8h hard cap) | 0 | yes |
| A1 scaffold + contracts | M | 1 | yes |
| A2 pipeline + oracle + invariants | **L** | 1 | yes |
| A3 staleness model | M | 2 | no |
| A4 eviction + baselines | M | 2 | no |
| A5 W1 generator | **L** | 2 | no |
| A6 W2 loader | M | 2 | no |
| A7 harness + metrics | **L** | 2 | no |
| A8 brackets | S | 4 | yes (gate 3) |
| A9 ablation | M | 4 | no |
| A10 sweeps | M | 4 | no |
| A11 analysis | M | 5 | no |
| A12 report | **L** (human) | 5 | — |
| A13 baseline 1-pager | S | any | no |

Four L cards: A2, A5, A7, A12. **Sanity-check these against the calendar before dispatch.**
Scope is the dominant risk on this project, not correctness — if the calendar does not
absorb four L cards plus six M cards, cut W2 at GATE 1 regardless of feasibility and drop
one sweep axis from A10.

---

## 4. Agent cards

### A0 — W2 feasibility spike

**Phase 0. Blocking. Hard timebox: 8 hours.**

**Mandate.** Determine whether Wikipedia revision history yields a §2.3-conformant trace
with a defensible `valid_until`. Produce a decision memo and a sample trace, or a documented
negative.

**Tasks.**
1. Pick ~30 questions whose answers are single facts on a page with an identifiable section.
   Name the QA source (SQuAD / Natural Questions / TriviaQA) and justify.
2. Pull each section's revision timeline.
3. **State the invalidation rule explicitly.** Proposal: the answer generated from revision
   `r` becomes invalid at the timestamp of the next revision that alters the sentence
   containing the answer string. Revisions touching only formatting, citations, or unrelated
   sentences do not invalidate.
4. Hand-label 20 (answer, revision-pair) cases as invalidating / non-invalidating. Report
   agreement between the automatic rule and the labels as a number.

**Files owned.** `workloads/w2_wikipedia/spike/`, `docs/w2-feasibility.md`.

**Acceptance criteria.**
- Memo states the rule in one paragraph, reports rule-vs-label agreement, and estimates
  full-loader build cost in hours.
- A 200-row `sample.jsonl` validating against §2.3, or a documented reason none exists.

**GATE 1 decision rule.** Proceed with W2 iff agreement ≥ 80% **and** estimated build ≤ 25h.
Otherwise cut W2, run W1-only, record the external-validity limitation in the report's
Discussion. **Decided once; not revisited.** A mid-project W2 revival is how schedules die.

**Forbidden.** Anything outside `workloads/w2_wikipedia/spike/` and `docs/`.

---

### A1 — Scaffold, CI, frozen contracts

**Phase 1. Blocking.**

**Mandate.** A reproducible repo with a pinned GPTCache fork, working CI, and the §2.1
contracts written verbatim.

**Tasks.**
1. Vendor GPTCache at a **pinned commit SHA** into `vendor/gptcache/`. Record the SHA and
   the pinned ONNX embedder version in `README.md`. Never modify vendored code.
2. **Re-verify every line reference in design §2.2** against the pinned SHA. Emit
   `docs/baseline-source-map.md`: each claim, its line range, a one-line quote. Correct any
   drift there. The design doc's numbers came from an unpinned read and **must not be quoted
   in the report until this file exists.**
3. `Dockerfile` + `environment.yml`, both producing a working `pytest` from a clean clone.
4. `.github/workflows/ci.yml`: lint, `pytest`, benchmark smoke (A7 fills the last; leave a
   documented stub).
5. `Makefile`: `install`, `test`, `bench-smoke`, `verify`.
6. Write `gptcache_ext/contracts.py` **exactly as §2.1**. Write all `__init__.py` files from
   §2.6 with imports for not-yet-existing modules commented out and labelled with the owning
   agent ID — this stops five agents racing on the same `__init__.py`.
7. `README.md` with a `<!-- BENCHMARK:A7 -->` … `<!-- /BENCHMARK:A7 -->` placeholder block.

**Acceptance criteria.**
- `docker build . && docker run <img> make test` passes from a clean clone.
- CI green on an empty suite.
- `docs/baseline-source-map.md` covers all six claims in design §2.2.
- `python -c "import gptcache_ext.contracts"` succeeds.

**Forbidden.** `vendor/gptcache/**` after import. Any `gptcache_ext/` module except
`contracts.py` and `__init__.py`.

---

### A2 — Pipeline seam, metadata, reference oracle, invariants

**Phase 1. Blocking. The most consequential card — everything downstream builds on it.**

**Tasks.**
1. `metadata.py` — additive `EntryMeta` persistence. Extend `CacheData`
   (`scalar_data/base.py`) with `cluster_id`, `answer_id`, `valid_until`, `regen_cost`,
   `size_bytes` **via subclass or adapter; never by editing vendored code**. Provide
   `get_meta(entry_id) -> EntryMeta` backed by `self.s.get_data_by_id`.
2. `pipeline.py` — `decide()` per §2.2 plus `NullGate`. **One shared helper called from both
   `adapt` and `aadapt`** — GPTCache duplicates hit/miss logic across sync and async paths
   and mirrored edits will drift.
3. `config.py` — one object carrying every knob the sweeps touch: gate on/off, eviction
   policy name, cache size, cluster count K, TTL confidence, λ source, seed.
4. `tests/oracle/reference_cache.py` — a naive, obviously-correct cache: a dict, an explicit
   `{entry_id: valid_until}` table, linear-scan nearest neighbour, same `Decision` return
   type. **Optimised for legibility, not speed** — a grader must be able to read it and agree
   it is right.
5. `tests/invariants.py` — a callable suite, invoked from unit tests *and* from every
   benchmark run:
   - entry count never exceeds budget after an insert completes;
   - `select_victim` returns `argmin value()` over the current set;
   - no entry served when `now - create_on > ttl_seconds` for its cluster;
   - **`age` derives from `create_on`:** a hot-but-old entry (high `freq`, recent
     `last_access`, old `create_on`) is classified stale;
   - **answer-key leak check:** `valid_until` appears nowhere in `gptcache_ext/` except
     `metadata.py`;
   - identical seed → identical decision sequence.
6. `tests/test_stock_parity.py` — 10,000 queries through pipeline + `NullGate` + LRU versus
   stock GPTCache. **Zero divergences required.**

**Acceptance criteria.**
- All the above green in CI.
- `pytest --cov=gptcache_ext.pipeline` ≥ 95% branch coverage.
- Parity test: exactly 0 divergences over 10k queries.
- Oracle and pipeline agree on decisions across a 5,000-query stub trace.

**Forbidden.** `vendor/**`, `gptcache_ext/staleness/**`, `gptcache_ext/eviction/**`,
`workloads/**`, `benchmarks/**`.

---

### A3 — Staleness model: clustering, fitter, gate

**Phase 2. Parallel.**

**Tasks.**
1. `clusters.py` — seeded k-means over query embeddings, `K` configurable. Persist centroids
   so assignment is stable across runs. Unseen query → nearest centroid. **Cluster assignment
   lives here and is consumed everywhere else, never recomputed** — divergent cluster identity
   between the gate and the eviction policy is the most likely integration bug at GATE 2.
2. `fitter.py` — from the `split == "calib"` portion of a trace, estimate `λ_c` per cluster by
   fitting an exponential survival curve to observed `valid_until - t` durations. Derive
   `ttl_seconds = -ln(confidence) / λ_c`. Emit `staleness_table.json`.
   **Three modes, one parameter, identical output format:**
   - `learned` — per-cluster fit;
   - `global` — one λ pooled across all clusters;
   - `oracle` — λ taken from the generator's true half-lives (W1 only).
   A8's entire experiment is running the same pipeline three times with this flag changed, so
   the modes must be genuinely interchangeable.
   Clusters with `n_obs < 30` fall back to global λ; record `n_obs` so the report can show how
   many were pooled.
3. `gate.py` — `TTLGate` implementing `Gate`. Reads `create_on`. One comparison.

**Acceptance criteria.**
- On a synthetic trace with known half-lives, fitted λ within 10% of truth for clusters with
  `n_obs ≥ 100`.
- `oracle` mode reproduces generator λ exactly.
- Gate tests cover: fresh, exactly-at-TTL boundary, expired, unseen cluster (falls back,
  never raises).
- **Explicit test that the gate ignores `last_access`.**
- Fitter deterministic: same trace + seed → byte-identical JSON.

**Forbidden.** `gptcache_ext/eviction/**`, `gptcache_ext/pipeline.py`, `benchmarks/**`,
`workloads/**`.

---

### A4 — Eviction policies: FreCoS and all baselines

**Phase 2. Parallel. Owns the entire eviction axis**, so the ablation table in A9 maps
one-to-one onto this card's outputs.

**Tasks.**
1. `eviction/frecos.py`:
   `value = log(1+freq) · log(1 + κ·regen_cost) · exp(-λ_c · age) / size_bytes`,
   `age = now - create_on`. Register as a named `EvictionBase` subclass through the
   registration hook at `eviction/manager.py:29-48` — **a hook, not an edit** to vendored code.
   Read metadata via A2's `get_meta()`; eviction natively sees only bare ids
   (`data_manager.py:338`).
2. `--no-size` flag dropping the `/size_bytes` divisor. This is an ablation row, so it must be
   a flag, not a code edit.
3. `eviction/baselines.py` — LRU and LFU wrappers exposing the same `EvictionPolicy` protocol,
   plus an adapter for **Biton & Friedman's released policy** (arXiv:2603.03301). Their
   implementation is used directly, not reimplemented.
   **Timebox the adapter to one day.** If it will not fit the harness in that time, substitute
   a documented LFU-with-cost variant and record the substitution — do not silently drop the
   comparator, it is the primary one.
4. **Budget is entry-count-based**, matching stock GPTCache. `size_bytes` is used inside
   `value()` only. No byte-budget eviction loop.

**Acceptance criteria.**
- `tests/test_frecos.py`: `freq=0` scores above zero (**cold-start regression** — the naive
  multiplicative form evicts new entries immediately); monotonicity in each of the four terms
  with others fixed; deterministic tie-break (oldest `create_on`, then lowest `entry_id`);
  `select_victim` == brute-force `argmin value` over 1,000 random entry sets.
- Property tests: of two entries identical but for `regen_cost`, the cheaper is evicted first;
  likewise larger `size_bytes` first, lower `freq` first, older `age` first.
- **Explicit test that `value()` never reads `last_access`.**
- A2's invariant suite passes when driven by each policy in this module.

**Forbidden.** `gptcache_ext/staleness/**`, `gptcache_ext/pipeline.py`, `vendor/**`,
`benchmarks/**`.

---

### A5 — W1 synthetic workload generator

**Phase 2. Parallel.**

**Tasks.**
1. `generator.py` — parameters: `n_tenants`, `n_clusters`, `n_queries`, `seed`, Zipf skew,
   per-cluster (half-life, regen-cost) distributions. Emits §2.3 JSONL with the `split` field
   set by a 30/70 cut on `t`.
2. Stream composition, each a tunable fraction: near-duplicate paraphrases within a cluster
   (stresses hit and false-hit), novel long-tail queries (stresses overhead and admission), and
   **time-shifted repeats of the same `answer_id`** — the only construct that exercises the
   staleness gate at all.
3. `calibrate.py` — fit the regen-cost distribution to the Azure LLM Inference Trace and the
   half-life distribution to update frequencies in a public news/catalog corpus. Emit
   `docs/w1-calibration.md` containing the two synthetic-vs-real overlay plots the report needs.

**Acceptance criteria.**
- Same seed → byte-identical trace file.
- `tests/test_w1.py`: schema-valid on every row; `t` monotonic; **at least one `valid_until`
  boundary crossed for every `answer_id` that repeats** (otherwise the gate is untestable);
  paraphrase pairs actually exceed the default similarity threshold under the pinned embedder;
  calibration and eval splits are disjoint in `t`.
- Calibration doc has both overlay plots, labelled axes, and one line naming the real
  distribution each was fitted to.

**Forbidden.** `gptcache_ext/**`, `benchmarks/**`, `workloads/w2_wikipedia/**`.

---

### A6 — W2 Wikipedia loader *(conditional on GATE 1)*

**Phase 2. Parallel. Runs only if GATE 1 passed.**

**Tasks.** Implement the invalidation rule exactly as fixed in `docs/w2-feasibility.md`.
**Cache raw revision data locally** so runs never depend on live API availability — a
reproducibility requirement, not a convenience. Emit ≥ 2,000 queries with the `split` field.

**Acceptance criteria.**
- Schema-valid trace, reproducible offline from the cached snapshot.
- `tests/test_w2.py`: A0's 20 hand-labelled cases classified correctly.
- `docs/w2-provenance.md`: dump date, QA source, invalidation rule.

**Forbidden.** Everything outside `workloads/w2_wikipedia/` plus its test and doc files.

---

### A7 — Benchmark harness and metrics

**Phase 2. Parallel. Depends on A2 only.**

**Tasks.**
1. `harness.py` — takes (trace, config, seed), replays in `t` order per the §2.5 simulation
   model, returns one §2.4 row. **Runs A2's invariant suite on every run**, not only in tests.
   Applies the 10% warmup exclusion.
2. `metrics.py`:
   - `stale_hit_rate` — served hits with `t_serve > entry.valid_until`, over total hits;
   - `false_hit_rate` — served hits with `entry.answer_id != query.answer_id`;
   - `cost_saved` — Σ `regen_cost` over **non-stale** hits. A stale hit saves nothing; it
     served a wrong answer, and counting it as savings would flatter the headline metric;
   - latency mean/p50/p95/p99, throughput;
   - **extension overhead** — cluster lookup + gate check, timed separately, own column;
   - **peak RSS and CPU%** via `resource`/`psutil`. Required by guideline §3 and easy to omit.
3. `pytest-benchmark` integration. Sample CSV and JSON committed under `benchmarks/samples/`.
4. Fill the `<!-- BENCHMARK:A7 -->` block in `README.md` with a "How to benchmark" section:
   one command reproducing a sample row. **Replace only inside the markers.**
5. Wire the smoke run into CI so **every commit reruns the suite** (guideline §3).

**Acceptance criteria.**
- One command reproduces a committed sample row: within noise on latency columns, **exactly**
  on every count and rate column.
- CI runs the smoke benchmark on push and fails on invariant violation.
- `tests/test_metrics.py`: a 20-query fixture with hand-worked expected hit rate, stale-hit
  rate, false-hit rate, and cost saved. Hand-worked, so the metric definitions are pinned by
  something other than the implementation.

**Forbidden.** `gptcache_ext/**`, `workloads/**`, `benchmarks/runners/**`, `README.md`
outside the A7 markers.

---

### A8 — Experiment 1: bracketing *(runs first; decides the story)*

**Phase 4. Blocking on GATE 2. Owns `benchmarks/runners/brackets.py` and `results/brackets/`.**

**Design.** W1, eval split only. Three `lambda_source` values (`global`, `learned`, `oracle`)
× 10 seeds, gate enabled, FreCoS eviction, cache size at the mid sweep point. Everything else
constant.

**Acceptance criteria.**
- `results/brackets/` holds 30 §2.4-conformant rows.
- `summary.md` reports median stale-hit-rate and cost-saved per `lambda_source` with bootstrap
  95% CIs, plus Mann-Whitney U for learned-vs-global.
- **A stated verdict:** does learned λ land strictly between global and oracle on
  stale-hit-rate, with CIs not overlapping global?

**This is a decision point, not just an experiment.** On a negative verdict, escalate to the
human before anything else runs: the report pivots to the characterization framing (design
§5.5) and A9/A10 are re-scoped to characterize *when* learned decay pays rather than to
demonstrate that it does.

**Forbidden.** All source directories; `results/` outside `brackets/`; runner files other
than `brackets.py`.

---

### A9 — Experiment 2: ablation

**Phase 4. Parallel with A10. Owns `benchmarks/runners/ablation.py` and `results/ablation/`.**

**Design.** W1 eval split, 10 seeds per row:

| Row | Gate | Eviction | Isolates |
|---|---|---|---|
| 1 | off | LRU | stock GPTCache |
| 2 | off | LFU | **the real floor** (Biton & Friedman: LRU is weak on semantic workloads) |
| 3 | off | Biton & Friedman policy | primary comparator |
| 4 | **on** | LFU | the gate alone |
| 5 | on | FreCoS | full stack |
| 6 | on | FreCoS `--no-size` | size normalization |

Row 5 repeated on W2 if it exists — single configuration, no sweep.

**Acceptance criteria.**
- `results/ablation/` with 60+ rows.
- `summary.md` reporting each row's delta **versus row 2, not row 1** — LRU is not the
  comparison of record.
- An explicit statement of whether the predicted interaction held: the gate should carry most
  of the stale-hit-rate improvement, with FreCoS's decay term contributing less on top of it
  than it does alone (design §3.2). A contradiction here means one of the two implementations
  is wrong and is the first place to look.

**Forbidden.** All source directories; `results/` outside `ablation/`; runners other than
`ablation.py`.

---

### A10 — Experiment 3: sweeps

**Phase 4. Parallel with A9. Owns `benchmarks/runners/sweeps.py` and `results/sweeps/`.**

**Design.** Three axes, full stack, 10 seeds per point, **one axis at a time — no full
factorial**:
- cache size in entries: 5 points spanning ~5%–80% of the working set;
- TTL confidence: {0.8, 0.9, 0.95, 0.99};
- cluster count K: {5, 10, 20, 50}.

**Acceptance criteria.**
- `results/sweeps/{cache_size,ttl_confidence,cluster_k}/`, each with a summary.
- Each summary names the effect direction and whether it is monotone.
- **A knee identified on the cache-size axis** — the report needs one operating point to anchor
  its headline numbers.
- The TTL-confidence axis produces the (stale-hit-rate, hit-rate) pairs that A11's trade-off
  curve is built from. This axis is therefore not optional even under schedule pressure; drop
  cluster K first if something must go.

**Forbidden.** All source directories; `results/` outside `sweeps/`; runners other than
`sweeps.py`.

---

### A11 — Analysis and figures

**Phase 5. Owns `analysis/` and `docs/experiments.md`.**

**Hard constraint, given up front rather than left to write-time judgment:** the result set
produces far more figures than 8–12 pages can hold. Promote **only the 3–4 findings with the
largest effect size and tightest CI** to headline figures. Everything else goes to a
supplementary CSV, cited by summary statistic, never plotted.

**Required figures.**
1. **Stale-hit-rate by policy** — the headline. Bars with CIs.
2. **The bracket** — global / learned / oracle on one axis.
3. **The correctness-versus-efficiency trade-off** — stale-hit-rate against hit rate as TTL
   confidence varies. **This is the honest core of the project.** The gate lowers hit rate by
   construction; the claim is about the exchange rate, not a uniform win. Get this one right.
4. **Cache-size sweep** with the knee marked.

Formatting per guideline §6: fonts ≥ 10 pt, labelled axes, legends, captions, consistent
sizing.

**Acceptance criteria.**
- `analysis/` regenerates every figure from `results/` with one command. **No hand-edited
  figures, ever.**
- Deliverable 4 drafted: per experiment — what ran, what came out, what it establishes.
- Every number traceable to a results-CSV row.

**Forbidden.** `results/**` (read-only), all source directories.

---

### A12 — Report

**Phase 5. Human-in-the-loop. Not fully delegated — this is the graded narrative.**

An agent may draft sections from `frecos-design.md` + A11 output; the human owns structure,
claims, and framing. Structure per guideline §6: Introduction (problem + related work) →
Design → Experimental Setup (**including the §2.5 simulation model and its limitations**) →
Results → Discussion → Conclusion & Future Work → **Appendix referencing all code and data
artifacts.**

**Pre-submission checklist.**
- [ ] Cortex cited by current title, with the v1 "Asteria" name noted.
- [ ] Biton & Friedman positioned as closest prior art, not a footnote.
- [ ] Every §2.2 line reference matches `docs/baseline-source-map.md`.
- [ ] No claim of statistical significance without a Mann-Whitney U behind it.
- [ ] The hit-rate cost of the gate stated plainly, not buried.
- [ ] Simulated-latency limitation stated in Experimental Setup.
- [ ] 8–12 pages.

---

### A13 — Baseline justification and related work

**Independent. Dispatch any time after A1. Owns `docs/baseline-justification.md` and
`docs/related-work.md`.**

Deliverable 1: one page from design §2 — features, default eviction policy, why GPTCache, why
not vCache, and the frozen-repo argument stated openly rather than disguised as community
momentum. Cites `docs/baseline-source-map.md` for source claims.

`related-work.md` collects the full positioning from design §3.3 for A12 to draw on.

**Forbidden.** Everything else.

---

## 5. Integration gates

| Gate | After | Check | Fail action |
|---|---|---|---|
| **1** | A0 | Agreement ≥ 80% **and** build ≤ 25h | Cut W2. W1-only. Note the limitation in Discussion. Not revisited |
| **2** | A3–A7 | All unit tests green; stock-parity 0 divergences; invariants pass under every policy in A4; `make bench-smoke` emits a valid CSV row on W1 | Fix before any experiment. **Never start experiments on a red build** |
| **3** | A8 | Learned λ strictly between global and oracle, CIs not overlapping global | Escalate to human. Re-scope A9/A10 to characterization |
| **4** | A9, A10 | Every planned row present; no NaNs; all seeds complete | Re-run missing cells only |
| **5** | A11 | Every figure regenerable; every number traceable | No hand-edited figures |

**Gate 2 is where integration bugs surface.** A3 and A4 are built against contracts, never
against each other. Budget explicit time here. The specific failure mode to look for: a gate
and an eviction policy that each pass their own tests but disagree about cluster identity —
which is why A3 owns cluster assignment and everyone else consumes it.

---

## 6. Traceability to course deliverables

| Guideline deliverable | Criterion | Produced by |
|---|---|---|
| §2 Baseline justification (1 p.) | — | A13 |
| §3 Benchmark suite + README + sample logs + CI | Reproducibility 30% | A7, A1 |
| §4 Extension code (feature branch) + unit tests | Correctness 40% | A2, A3, A4 |
| §5 Experiments PDF | Performance 15% | A8, A9, A10, A11 |
| §6 Report 8–12 pp + appendix | Clarity 15% | A12 |
| §6 Clean repo, Dockerfile, CI | Reproducibility 30% | A1 |
| §4 Upstream PR *(optional)* | bonus | Deferred; byte-budget eviction only |

The two heaviest criteria (Correctness 40%, Reproducibility 30%) are carried by A1, A2 and A7
— the least glamorous cards on the board. They are scheduled first and none is optional.

---

## 7. Risk register

| Risk | Trigger | Response |
|---|---|---|
| W2 infeasible | GATE 1 fails | W1-only; state the external-validity limit. Decided once |
| Learned λ ≈ global λ | GATE 3 negative | Pivot to characterization (design §5.5). Pre-committed; not a failure |
| B&F policy won't adapt | > 1 day in A4 | Documented LFU-with-cost substitute; record it. Never silently dropped |
| Gate and eviction disagree on cluster identity | GATE 2 | A3 owns assignment; everyone else consumes. Never recomputed |
| `last_access` used for age | Any time | A2 invariant + A3 test + A4 test. Three checks because the bug is silent and invalidates every staleness number |
| Cache logic reads `valid_until` | Any time | A2's grep-based leak check in the invariant suite |
| Scope creep toward cut components | Any time | Cut list is design §3.4. Additions require dropping something else |
| Four L cards exceed the calendar | Before dispatch | Cut W2 at GATE 1 regardless of feasibility; drop cluster-K sweep from A10 |
| Report exceeds 12 pages | A12 | A11's 3–4 figure constraint. Enforced at analysis time, not writing time |

---

## 8. Definition of done

- [ ] `git clone && docker build && make verify` green from scratch on a clean machine.
- [ ] Every experiment in §4 reproducible by one command from the README.
- [ ] All seven deliverables in §6 present.
- [ ] No number in any document without a results-CSV row behind it.
- [ ] Invariant suite green on every run in `results/`, not merely in CI.
- [ ] `docs/baseline-source-map.md` matches the pinned SHA and every line reference the report
      quotes.
