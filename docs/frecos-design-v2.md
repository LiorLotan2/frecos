# FreCoS: A Learned Staleness Model for Semantic Caches — Design Spec

Date: 2026-07-25

"FreCoS" (**Fre**shness- and **Co**st-aware **S**erving) is a name coined for this project,
not an established term from prior literature.

---

## 1. Problem statement

Semantic caches are evaluated on hit rate, latency, and at best false-hit rate. None of
these distinguishes a correct hit from a stale one. A cache serving 60% hits, a fifth of
which are no longer true, is indistinguishable on every existing dashboard from one serving
60% correct hits.

Two concrete gaps follow:

1. **No staleness concept in the serve path.** A cached answer about a daily-refreshed fact
   is served indefinitely. "Found in cache" is treated as "correct."
2. **No cost term in eviction.** LRU and LFU evict by recency or count. Two entries with
   identical access patterns but very different regeneration cost are evicted identically.

Industry position: frontier-model APIs (OpenAI, Anthropic, Gemini, Bedrock) do exact-prefix
KV caching with wall-clock TTL and no similarity matching. Semantic-caching products
(Portkey, Redis LangCache, GPTCache) use one fixed global cosine threshold with plain
TTL/count eviction. The research literature is substantially ahead of the products (§3.3);
this project positions against the literature.

---

## 2. Baseline: GPTCache

### 2.1 Selection rationale

GPTCache is frozen: last release v0.1.44 (Aug 2024), 75 open issues, 16 open PRs, and a
README note that new model/API support is no longer added. The case rests on architecture
and control properties, not activity:

- **Stable target.** A frozen API is a better scientific control than a moving one. The
  baseline measured in week 3 is byte-identical to the one in week 12.
- **Architectural fit, verified by source read.** Every component to be modified sits behind
  a registered, named interface (§4). The extension is additive config.
- **Comparability.** It is the baseline the adjacent literature uses — including Biton &
  Friedman (§3.3), whose released policies are this project's primary comparator.
- **CPU-only and deterministic** with the ONNX embedding backend.

**Alternative considered and rejected:** vCache (arXiv:2502.03771, ICLR 2026). Rejected
because per-prompt threshold learning is vCache's own contribution and eviction is not its
focus. Named explicitly in the one-page justification.

### 2.2 Baseline behavior (verified against source)

- Single global `similarity_threshold`, default 0.8 — `gptcache/config.py:40`.
- Hit decision — `adapter.py:98-107`, `adapter.py:173` (`if rank_threshold <= rank`).
- Eviction is **count-based only** (LRU/LFU/FIFO/RR) —
  `gptcache/manager/eviction/memory_cache.py:43-59`. No metadata stored with evicted keys
  (`self._cache[obj] = True`).
- Timestamps `create_on` and `last_access` are stored but never read
  (`scalar_data/base.py:70-71`, `sql_storage.py:64-65`) — dead columns this project
  repurposes.
- No admission control; every miss is inserted — `adapter.py:258-273`.
- No cost accounting, no false-hit or stale-hit metrics — only op timers (`report.py`).

Line references to be re-verified against the pinned commit before the report quotes them.

This section expands into the one-page baseline-justification deliverable.

---

## 3. Contribution

**One learned artifact, two consumers.** The project fits a per-cluster staleness model and
uses it at both ends of the cache lifecycle: as a hard validity gate when serving, and as a
soft decay term when evicting. The metric that makes both visible is the headline claim.

Scope note: an earlier draft included a third component (calibrated per-cluster similarity
thresholds). It is excluded — per-cluster thresholding is published (Category-Aware,
arXiv:2510.26835) and is a lossy special case of vCache's per-embedding threshold, so the
cost of building and calibrating it exceeded what it could contribute. Listed as future work.

### 3.1 M1 — stale-hit-rate as a first-class cache metric (headline)

**Claim:** semantic caches are evaluated on metrics that cannot distinguish a correct hit
from a stale one. This project defines **stale-hit-rate** — the fraction of *served* hits
whose content was no longer valid at serve time — builds the apparatus to measure it, and
shows that LRU, LFU, and a published semantic-aware policy are all blind to it in workloads
where it is the dominant error mode.

Measuring it requires ground-truth answer validity by time, which no public QA dataset
carries. §5.1 supplies it by two independent routes, one of them external, so the metric
does not rest solely on a self-authored generator.

### 3.2 The staleness model and its two consumers

Cluster assignment: k-means over cached-query embeddings, fixed at cache-build time. No
online re-clustering — a deliberate reproducibility choice, since dynamic re-clustering
makes runs non-deterministic. Per cluster `c`, fit from observed staleness in the
calibration split:

- `λ_c` — exponential decay rate of answer validity.
- `TTL_c` — the age at which validity drops below a configured confidence, derived from
  `λ_c`. One fitted quantity, two derived parameters.

**Consumer A — validity gate (serve path).**

```
on candidate hit:
    if (now - entry.create_on) > TTL_cluster:
        treat as MISS, recompute, refresh entry
        record stale_hit_prevented += 1
    else:
        serve cached answer
```

**Consumer B — eviction value.**

```
value(entry) = log(1 + freq) · log(1 + κ · regen_cost) · exp(-λ_cluster · age) / size
```

Evict lowest `value`. Tie-break by oldest `create_on` (deterministic).

| Term | Definition | Requirement |
|---|---|---|
| `freq` | Decayed access count | `log(1+·)` mandatory: a freshly-admitted entry has freq = 0 and must not score 0, or it is evicted on the next insert |
| `regen_cost` | `output_tokens × price_per_token`, recorded at write time | Recorded, never estimated. Log-scaled with fixed κ so the heavy-tailed cost distribution cannot dominate |
| `age` | `now - create_on` | **Never `last_access`.** Content staleness is a property of generation time; `last_access` would make a popular stale entry permanently fresh. Asserted by regression test (§5.4) |
| `size` | Entry size in bytes, recorded at write time | Value is per byte. Recording `size_bytes` does **not** require byte-budget eviction — the budget stays entry-count-based (§4) |

Because the gate already refreshes anything past `TTL_c`, the decay term in `value()` is not
performing staleness prevention — it acts as a soft prior over still-valid entries, favoring
those with more remaining useful life. This is the design, not an accident, and the ablation
is expected to show the gate carrying most of the stale-hit-rate improvement.

### 3.3 Prior art and the exact delta

**Biton & Friedman, "From Exact Hits to Close Enough" (arXiv:2603.03301, Feb 2026) —
closest prior art.** Proves optimal offline semantic-cache eviction is NP-hard, gives
polynomial-time heuristics, and presents online policies combining recency, frequency, and
locality, evaluated on GPTCache with code released. Two consequences that shape this plan:

- Their finding that LRU is a poor policy for most semantic workloads, and that
  frequency-based policies are strong baselines, means **LFU-class comparators are the
  floor**. An improvement measured only against LRU is not a result.
- Their released implementation is the **primary comparator** (§5.2) — used directly rather
  than reimplemented.

The delta: their policies combine recency, frequency, and locality, all of which are
*access-pattern* signals. FreCoS adds two signals orthogonal to access pattern —
regeneration cost and content validity over time — and evaluates against a correctness
metric their setting does not define.

**Cortex (NSDI '26; arXiv:2509.17360, v1 titled "Asteria")** — its LCFU policy scores
entries as `log(freq+1)·log(cost·10³+1)·log(lat+1)·log(staticity+1)/size` with a TTL purge:
multiplicative, cost- and frequency- and staleness-aware, size-normalized, for eviction.
**Cite by the current title; the v1 name still appears in others' bibliographies.** The
delta FreCoS claims is narrow and specific: **Cortex's staleness term is an LLM-assigned
static staticity score (1–10) plus a user-defined TTL; FreCoS's is a decay rate learned per
cluster from observed staleness.** Learned versus assigned. §5.3's brackets test whether
that learning does any work. Cortex's LCFU is *not* reimplemented as a comparator — its
formula carries remote-tool-call latency metadata absent from this setting, and a faithful
port is a project of its own.

**Others.** GDSF (Cherkasova & Ciardo, HPCN 2001) — cost × frequency / size with
global-clock aging, no freshness semantics. Category-Aware (arXiv:2510.26835) —
per-category TTLs, load-based rather than learned-from-staleness, no stale-hit-rate metric.
FreshCache (arXiv:2607.04281) — RAG-specific per-tier probabilistic staleness gate; same
lineage, positioned as probabilistic risk budget versus this project's hard learned gate
plus a named serving-correctness metric. SCALM (arXiv:2406.00025) — cluster-based entry
significance with its own eviction strategy. MeanCache (arXiv:2403.02694) — cost-motivated,
eviction is not its contribution.

### 3.4 Out of scope

- **W-TinyLFU admission.** Prior art (TinyLFU, arXiv:1512.00727; shipped in Caffeine,
  Ristretto, Moka) makes this an engineering port with no research delta.
- **Calibrated per-cluster similarity thresholds.** See §3 scope note.
- **Dynamic re-clustering.** Breaks determinism; §3.2.

All three are grounded future work.

---

## 4. Implementation seams

The serve-path seam is built once, in phase 2, before the gate exists.

```python
# gptcache_ext/pipeline.py
candidate = vector_search(query)
if candidate is None:              -> MISS
if candidate.rank < threshold:     -> MISS
if is_stale(candidate):            -> MISS + refresh   # gate plugs in here
else:                              -> HIT
```

`is_stale()` is a no-op stub by default, so a pipeline with the gate disabled is
behaviorally identical to stock GPTCache — itself an invariant test (§5.4).

| Component | Stage | Integration point |
|---|---|---|
| Pipeline | match / serve | New `gptcache_ext/pipeline.py`. `adapter.py:173` and its `aadapt` twin both delegate through **one shared helper** — no mirrored edits across the sync/async duplication |
| Validity gate | serve | Implements `is_stale()`; reads `create_on` |
| FreCoS eviction | eviction | New `EvictionBase` subclass in `gptcache/manager/eviction/`, registered in `eviction/manager.py:29-48`. Requires `regen_cost`, `cluster_id`, `size_bytes` on `CacheData` (additive fields, `scalar_data/base.py:60-97`). Eviction currently sees bare ids (`data_manager.py:338`), so FreCoS reads metadata back via `self.s.get_data_by_id` |
| Staleness fitter | offline | Standalone module; consumes the calibration split, emits a per-cluster `{λ_c, TTL_c}` table loaded by both consumers |

**Eviction budget stays entry-count-based**, matching stock GPTCache. `size_bytes` is
recorded and used inside `value()`, but no byte-budget eviction loop is built. This removes
a subsystem from the critical path; sweeps are reported in entries (§5.2). Byte-budget
eviction is the optional upstream PR (§6), not a dependency.

Interface compatibility: all changes are additive config. A user who does not opt in gets
stock behavior, asserted by test.

---

## 5. Experiment plan

### 5.1 Workloads

**W1 — synthetic generator** (deterministic, seeded, ships in repo). N tenants × K topic
clusters; each cluster carries a ground-truth staleness half-life and regen-cost
distribution. Query stream mixes near-duplicates within a cluster, novel long-tail queries,
and time-shifted repeats. Distributions calibrated against a public LLM trace (Azure LLM
Inference Trace) for regen cost, and against observed content-update frequency in a public
news/catalog corpus for half-life. The report plots synthetic against real distributions as
a credibility check. Carries all sweeps and the full ablation.

**W2 — Wikipedia revision-history QA.** Answer validity by time is derivable from edit
timestamps: an answer generated at T is stale at T′ if the relevant section was edited
between them. Externally-derived staleness ground truth. Smaller and noisier than W1 and
will not support sweeps — one headline stale-hit-rate comparison only. **Highest
value-per-hour item in the plan: it removes the objection that all staleness results are
self-generated. Scheduled first and de-risked before anything else is built.**

### 5.2 Runs

- **Baselines: LFU and Biton & Friedman's released policy** (arXiv:2603.03301). LRU is
  reported for continuity with GPTCache's default but is not the comparison of record — the
  same authors have published that it is a weak baseline on semantic workloads.
- Vanilla versus extended (gate + FreCoS eviction), identical workload, on W1 and W2.
- **Ablation, three rows:** baseline → +gate → +gate+eviction. Plus one variant row: FreCoS
  eviction without the `/size` term.
- **Sweeps, three axes:** cache size (in entries), TTL confidence level, cluster count K.

### 5.3 Validity of the learned model

λ and TTL are learned from ground truth and stale-hit-rate is measured against ground truth.
Two guards, both mandatory:

1. **Temporal split.** λ and TTL fit on the first 30% of the trace; all reported metrics
   computed on the remaining 70%. No parameter is fit on data it is evaluated on.
2. **Bracketing runs.** λ-oracle (true half-life known) as upper bound, λ-global (one value
   for all clusters) as lower bound. Learned-λ must land meaningfully between them.
   **Scheduled first among the experiments** — this is the test of the core claim, and if
   learned-λ does not beat λ-global the framing changes (§5.5) while there is still time.

Deferred to future work: mis-specification under injected drift, held-out clusters.

### 5.4 Correctness artifacts

1. **Reference oracle.** A naive, obviously-correct implementation (dict plus explicit
   validity table) run in lockstep on the same query stream. Any divergence in hit/miss
   decisions is a test failure.
2. **Invariants**, asserted on every benchmark run, not only in unit tests:
   - entry budget never exceeded after an insert completes;
   - eviction victim is `argmin value()` over the current set;
   - no entry is served with `now - create_on > TTL_cluster`;
   - `age` computed from `create_on`, never `last_access` — regression test with a
     hot-but-stale entry;
   - pipeline with the gate disabled and eviction set to LRU produces decisions
     byte-identical to stock GPTCache.
3. **Determinism.** Same seed produces a byte-identical results CSV. Asserted in CI.

### 5.5 Metrics, statistics, framing

**Metrics.** Correctness: stale-hit-rate (headline), false-hit-rate, stale-hits-prevented.
Efficiency: hit-rate, cost saved (regen-cost-weighted), latency (mean, p95, p99),
throughput. Resource: peak RSS, CPU utilization. **Extension overhead:** added per-request
time for cluster lookup and staleness check, measured separately from the net result.

**Statistics.** Every reported configuration runs **N = 10 seeds**. Results are medians with
bootstrap 95% confidence intervals; differences tested with Mann-Whitney U. The phrase
"statistically significant" appears only where this test was run.

**Expected trade-off, stated in advance.** The gate converts stale hits into misses, so it
*lowers* hit rate and raises mean latency by construction. The claim is that it buys
correctness at a bounded efficiency cost, and that cost-aware eviction repays part of that
cost in cost-saved terms. The report presents this as a trade-off curve, not a uniform win.

**If the result is negative** — learned λ does not beat λ-global, or the decay term
contributes nothing on top of the gate — the report pivots to the characterization result:
*under what degree of cluster half-life heterogeneity does a learned decay begin to pay?*
Fixed now, before results exist.

### 5.6 Execution phases

Each phase gates on tests passing plus results being read.

1. **De-risk W2 (spike, first).** Establish that the Wikipedia revision-diff →
   answer-invalidation mapping is tractable. If it is not, W2 is cut and §5.1 falls back to
   W1 alone with the external-validity limitation stated plainly. Nothing else is built
   until this resolves.
2. **Scaffold (sequential, blocking).** Fork GPTCache at a pinned commit; Dockerfile /
   environment.yml; CI; pytest harness; the §4 pipeline with a stub gate; reference oracle
   and invariant suite.
3. **Build (parallel).** (a) validity gate + staleness fitter; (b) FreCoS eviction policy;
   (c) W1 generator and W2 loader. No shared files — the seam was fixed in phase 2.
4. **Experiments.** Bracketing runs (§5.3) first, then ablation, then the three sweeps.
   Independent result directories, no shared state.
5. **Analysis and report (human-in-the-loop).** Mandate for the analysis step: surface only
   the **3–4 findings with the largest effect size and tightest confidence interval** as
   headline figures; everything else goes to a supplementary CSV cited by summary statistic,
   not plotted.

---

## 6. Deliverables

1. **Baseline justification** — 1-page PDF from §2, including the vCache alternative.
2. **Benchmark suite** — `benchmarks/` plus a README "how to benchmark" plus sample
   CSV/JSON.
3. **Extension code** — feature branch, `gptcache_ext/` package (pipeline, validity gate,
   staleness fitter, FreCoS eviction), unit tests per component, reference oracle, invariant
   suite.
4. **Experiments PDF** — per-experiment results, significance, and what each establishes,
   including the bracketing runs.
5. **Final report PDF, 8–12 pages** — Introduction (problem and related work) → Design →
   Experimental Setup → Results → Discussion (the correctness/efficiency trade-off,
   parameter sensitivity, excluded components and why) → Conclusion and Future Work.
   **Appendix referencing all code and data artifacts.**
6. **Clean GitHub repo** — README, Dockerfile / environment.yml, CI running benchmarks and
   invariants on every commit.
7. **Optional stretch — upstream PR.** GPTCache's PR queue is 16 deep and stale; a merged PR
   within a semester is not a plan. If attempted, the candidate is **byte-based eviction
   accounting**: it fixes a defect the maintainers have documented, is small, and is
   independent of the research claim. Never blocking.

---

## 7. Report throughline

*Semantic caches are graded on hit rate, which cannot distinguish a correct hit from a stale
one. We name and measure that error — stale-hit-rate — show that LFU and a published
semantic-aware policy are both blind to it, and demonstrate that a single learned
per-cluster staleness model, applied as a serving gate and an eviction prior, reduces it at
a bounded and measured efficiency cost.*

Future work, grounded: dynamic re-clustering under drift; calibrated per-cluster similarity
thresholds; fuzzy-cluster W-TinyLFU admission; probabilistic staleness budgets in the
FreshCache style as an alternative to a hard gate.

---

## 8. Open items before implementation

- **Scope W2** — which Wikipedia QA set, and how the revision-diff → answer-invalidation
  mapping is defined. Least certain item; phase 1 spike.
- **Read Biton & Friedman (arXiv:2603.03301) in full** — closest prior art, released code is
  the primary comparator, and the paper's own baseline findings constrain §5.2.
- **Read Cortex (NSDI '26 / arXiv:2509.17360) §4.3 in full** — direct prior art for the
  eviction value function. Confirm the LCFU section is unchanged in the NSDI version before
  the report quotes the formula.
- **Read FreshCache (arXiv:2607.04281) and Category-Aware (arXiv:2510.26835) in full** —
  both bear directly on the validity gate.
- **Pin the GPTCache commit** and re-verify all §2.2 line references against it.

Citations verified: 2603.03301 (Biton & Friedman, Feb 2026), 2509.17360 (Cortex, NSDI '26;
v1 titled "Asteria"), 2502.03771 (vCache, ICLR 2026), 2510.26835, 2607.04281, 2406.00025,
2403.02694, 1512.00727.
