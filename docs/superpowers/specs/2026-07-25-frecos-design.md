# FreCoS: Freshness- and Cost-Aware Semantic Cache — Design Spec

Status: DRAFT — awaiting user review
Date: 2026-07-25

"FreCoS" (Frequency-Cost-Staleness eviction) is a name coined for this project, not an
established term from prior literature — stated as such in the report, not implied
otherwise.

## 1. Problem statement

Production LLM-serving systems (multi-tenant, per-geo, catalog-driven — the kind of
setup found at any AEO/answer-engine product) face three caching failure modes that
existing open-source semantic caches do not address:

1. **One global similarity threshold** is either too loose (false hits: near-duplicate
   queries across different topics get the wrong cached answer) or too tight (misses:
   legitimate paraphrases recompute).
2. **No staleness concept.** A cached answer about a daily-refreshed catalog fact can be
   served long after it stopped being true. Existing caches treat "found in cache" as
   correct; they never ask "is this entry still fresh enough to serve as this answer?"
3. **No cost term in eviction.** LRU/LFU evict by recency/count only. Two entries with
   identical access patterns but wildly different regeneration cost (short vs. long
   completions, cheap vs. expensive model) are evicted identically.

Industry confirms this is unclaimed territory (see `docs/related-work.md`, built from
research below): frontier-model APIs (OpenAI, Anthropic, Gemini, Bedrock) do exact-prefix
KV caching with plain wall-clock TTL, no similarity matching at all. Semantic-caching
products (Portkey, Redis LangCache, GPTCache) use one fixed global cosine threshold and
plain TTL/count eviction — none adapt per topic, none gate on content freshness, none
weigh eviction by cost.

## 2. Baseline: GPTCache

Chosen for:
- Maturity: established OSS semantic-cache library, pluggable architecture.
- Ease of modification: clean seam per component (see §4), verified by direct source read.
- CPU-only, deterministic — required for reproducibility (30% of grade).

Baseline behavior (verified against GPTCache source):
- Single global `similarity_threshold` (default 0.8), `gptcache/config.py:40`.
- Hit decision: `adapter.py:98-107`, `adapter.py:173` (`if rank_threshold <= rank`).
- Eviction: count-based only (LRU/LFU/FIFO/RR), `gptcache/manager/eviction/memory_cache.py:43-59`.
  No metadata stored with evicted keys (`self._cache[obj] = True`).
- Timestamps (`create_on`, `last_access`) are stored but never read
  (`scalar_data/base.py:70-71`, `sql_storage.py:64-65`) — dead columns we repurpose.
- No admission control: every miss is inserted (`adapter.py:258-273`).
- No cost, no false-hit/stale-hit metrics — only op timers (`report.py`).

This becomes the one-page baseline-justification deliverable (§6 below), expanded from
this section.

## 3. Extension: 3 components, ranked by contribution

Prior-art check (adversarial, arxiv-verified) puts these at different novelty tiers.
Framing reflects that honestly — this is the actual claim-to-fame the report has to sell.

### 3.1 FreCoS — cost- and freshness-aware eviction (headline contribution)

Novel **combination**: no existing eviction policy fuses frequency × regeneration cost ×
a **per-cluster learned freshness decay**.

```
value(entry) = freq(entry) × regen_cost(entry) × freshness(age(entry), λ_cluster)
freshness(age, λ) = exp(-λ · age)
```

- `regen_cost` = `output_tokens × price_per_token` at write time (recorded, not estimated).
- `λ_cluster` learned per semantic cluster from observed staleness (cluster = k-means over
  cached-query embeddings, fixed at cache-build time — no online re-clustering, keeps this
  tractable and reproducible).
- Evict lowest `value(entry)`.

**Scoping tradeoff, stated up front (not discovered later):** static clustering means
`λ_cluster`/`TTL_cluster` degrade under semantic drift (topics shifting over a run). This
is a deliberate reproducibility choice — dynamic re-clustering makes runs non-deterministic
and harder to reproduce (30% of grade), which outweighs the realism cost for this project's
scope. Stated explicitly in the report's Discussion and named as the lead Future Work item
(§7), not left as an implicit limitation.

Nearest prior art: GDSF (Cherkasova & Ciardo, HPCN 2001) — cost×frequency with global-clock
aging, no freshness semantics, no clustering. SCALM (arXiv:2406.00025) — clusters for cache
admission, not eviction value. MeanCache (arXiv:2403.02694) — cost-motivated, eviction is
not its contribution. FreCoS's specific fusion (freq × cost × per-cluster learned decay,
for eviction) is not published.

### 3.2 C2 — stale-hit correctness gate (second contribution)

Reframes staleness as a **correctness** problem, not a miss-rate problem:

```
on candidate hit:
    if age(entry) > TTL_cluster:
        treat as MISS, recompute, refresh entry
        record stale_hit_prevented += 1
    else:
        serve cached answer
```

`TTL_cluster` learned per cluster from observed ground-truth staleness in the synthetic
workload (§4). Introduces **stale-hit-rate** as a first-class correctness metric: the
fraction of served hits that were in fact stale (measurable only because the synthetic
workload knows ground truth — see §4.1).

Nearest prior art: Category-Aware Semantic Caching (arXiv:2510.26835, Oct 2025) — per-
category TTLs, but load-based not learned-from-staleness, and reports no stale-hit-rate
metric. FreshCache (arXiv:2607.04281, 2026) — RAG-specific, per-tier probabilistic
staleness gate; complementary axis (probabilistic vs. our hard learned-TTL gate). vCache
(arXiv:2502.03771) — gates on semantic mismatch, not temporal staleness. Combination
(learned per-cluster hard TTL gate + named stale-hit-rate metric) is not published as such.

### 3.3 C1 — calibrated per-cluster similarity threshold (supporting contribution)

Per-cluster threshold **alone** is already published (Category-Aware, arXiv:2510.26835) and
is a provably lossy special case of vCache's per-embedding threshold — a reviewer correctly
calls plain per-cluster thresholding "trivial." The survival path is an explicit
**confidence-calibration layer**: threshold is not a static per-cluster constant but a
per-cluster estimate with a shrinkage correction for low-sample clusters —

```
threshold_cluster = prior_threshold + (n_cluster / (n_cluster + k)) × (observed_optimal - prior_threshold)
```

(hierarchical shrinkage: small-`n` clusters lean on the global prior, large-`n` clusters
converge to their own optimum — the statistical case for pooling that per-embedding
thresholds can't make, since each embedding sees too few hits to calibrate alone). This is
framed in the report as an adaptation, not an independent novel idea — see §7 (report
story), Related Work subsection.

### Dropped: W-TinyLFU admission (C3)

Considered and cut. Prior art (TinyLFU, arXiv:1512.00727; shipped in Caffeine/Ristretto/
Moka) makes this an engineering port with no research delta beyond swapping the counted
key from exact to fuzzy-cluster. Cutting it keeps the ablation focused on the two real
combinations (FreCoS, C2) plus one calibrated supporting piece (C1), matching the
"3 components, cleanly ablatable" scope instead of diluting across 4.

## 4. Implementation seams (GPTCache)

| Component | Lifecycle stage | GPTCache integration point |
|---|---|---|
| C1 | match / hit decision | Replace global `similarity_threshold` lookup at `adapter.py:173` with a per-cluster threshold lookup; threshold table computed offline from cluster stats. |
| C2 | serve | Insert staleness check at `adapter.py:173`, before returning a hit — reads `create_on`/`last_access` (already stored, currently unused). |
| FreCoS | eviction | New `EvictionBase` subclass in `gptcache/manager/eviction/`, registered in `eviction/manager.py:29-48`. Needs `regen_cost` and `cluster_id` on `CacheData` (additive fields, `scalar_data/base.py:60-97`) — eviction currently only sees bare ids (`data_manager.py:338`), so FreCoS reads back cost/cluster via `self.s.get_data_by_id` at eviction time. |

Both sync `adapt` and async `aadapt` code paths need the same C2/eviction wiring —
GPTCache duplicates hit/miss/save logic between them.

Interface compatibility: all three components are additive config (new `EvictionBase`
subclass registered by name, new optional per-cluster threshold table, new optional
staleness gate) — a user who doesn't opt in gets stock GPTCache behavior unchanged. This
is what keeps a PR back to GPTCache upstream realistic (the guideline's "exceptional 100"
path) rather than aspirational.

## 5. Experiment plan

### 5.1 Workloads

**Primary — synthetic Discover-like generator** (deterministic, seeded, ships in repo):
- N tenants × M geos × K topic clusters.
- Each cluster has a ground-truth **staleness half-life** (some clusters = catalog facts
  that change daily, others = stable FAQ-style answers) and a ground-truth **regen cost**
  (some answers are one-line, some are long-form).
- Query stream mixes: repeated near-duplicates within a cluster (stresses hit/miss +
  false-hit), novel long-tail queries (stresses cache overhead / admission), and
  time-shifted repeats of the same query (stresses staleness gate — this is the only way
  to measure stale-hit-rate, since it requires knowing ground truth answer validity by time).
- This ground truth is what makes stale-hit-rate measurable at all — no public dataset
  carries "is this answer still true at time T" labels.

**Realism risk and mitigation.** Stale-hit-rate and cost-saved both depend on the
generator's staleness-half-life and regen-cost distributions being credible, not
hand-picked. Mitigation: calibrate both distributions against a public LLM trace dataset
(e.g. Azure LLM Inference Trace, or OpenAI/Anthropic usage-pattern reports where available)
rather than inventing constants — regen-cost distribution from real token-length/latency
traces, staleness half-life from a defensible proxy (e.g. observed content-update
frequency in a public catalog/news dataset) since no trace directly labels "answer
half-life." The report must show the synthetic distribution plotted against the real trace
distribution it's calibrated from, as a credibility check — this is load-bearing for the
Performance Gain grade (15%), since an unrealistic generator undermines any claimed gain.

**Secondary — public QA dataset** (e.g. an existing open QA/paraphrase set GPTCache
benchmarks already use) for external validity on hit-rate/latency, without staleness
claims (no ground-truth staleness labels available there).

### 5.2 Runs

- Vanilla GPTCache (LRU baseline) vs. extended (FreCoS+C2+C1), identical workload, fixed
  seed.
- Parameter sweep: cache size (50MB/100MB/200MB), θ (per-cluster threshold prior), TTL
  prior, cluster count K.
- Ablation: baseline → +C1 → +C2 → +FreCoS, and each leave-one-out from the full stack.

### 5.3 Metrics

hit-rate, false-hit-rate, stale-hit-rate, cost saved (regen-cost-weighted), latency
(mean/p95/p99), throughput.

### 5.4 Execution model — subagents

Implementation and experiments run as separate, independently-verifiable phases, each
delegated to a subagent with a narrow, checkable mandate (per `superpowers:
dispatching-parallel-agents`):

1. **Scaffold phase (1 agent, sequential):** fork GPTCache into this repo, set up
   Dockerfile/environment.yml, CI skeleton, pytest harness. Nothing else touches the repo
   until this lands — everything downstream depends on the fork existing.
2. **Component build (3 agents, parallel, one per component — C1, C2, FreCoS):** each
   agent owns one seam from §4, writes the code + its own unit tests, on its own branch/
   worktree to avoid file collisions (`adapter.py` is touched by all three — isolate with
   `git worktree`, merge sequentially after each is green).
3. **Workload build (1 agent):** synthetic generator + loader for the public secondary
   set. Runs in parallel with phase 2 — no shared files.
4. **Benchmark harness (1 agent):** pytest-benchmark scripts, CSV/JSON logging, CI wiring.
   Depends on phase 1 only; can run parallel to phases 2–3, merges last.
5. **Experiment execution (1 agent per sweep axis, parallel, after 2+3+4 merged):** cache-
   size sweep, threshold/TTL sweep, ablation matrix — each is an independent set of
   benchmark runs writing to its own results directory, no shared state.
6. **Analysis (1 agent):** consumes all results directories, produces plots (hit-rate
   curves, latency distributions, relative-improvement tables) and the experiments PDF.
   Full sweep × ablation matrix produces far more figures than an 8–12 page report can
   hold — explicit mandate: surface only the 3–4 most statistically significant findings
   (largest effect size, tightest confidence interval) as the headline figures; every other
   result goes into a supplementary CSV/appendix, cited by summary statistic, not plotted.
   This constraint is given to the agent directly, not left to its judgment at write time.
7. **Report-writing (sequential, human-in-the-loop):** the 8–12 page report is drafted
   from the analysis output + design spec, reviewed by the user before submission — not
   subagent-authored end to end, since this is the graded narrative.

Each phase gate: unit tests pass + a short self-check before the next phase starts (this
mirrors `verification-before-completion` — no phase is declared done on an agent's say-so
alone; results are read, not trusted blind).

## 6. Deliverables (mapped to guideline §1–7)

1. **Baseline justification** — 1-page PDF, from §2 above.
2. **Benchmark suite** — `benchmarks/` + README "how to benchmark" + sample CSV/JSON
   (guideline §3).
3. **Extension code** — feature branch, `gptcache_ext/` package (C1, C2, FreCoS), unit
   tests per component (guideline §4).
4. **Experiments PDF** — per-experiment results + significance + what each tells us
   (guideline §5).
5. **Final report PDF, 8–12 pages** — Introduction (problem + related work) → Extension
   Design (motivation + the 3-component story, honest novelty framing from §3) →
   Experimental Setup → Results → Discussion (trade-offs, parameter sensitivity,
   including the C1/dropped-C3 novelty-tier honesty as a discussion point, not hidden) →
   Conclusion & Future Work (C3/admission control as grounded future work; note we
   deliberately scoped it out and why) (guideline §6).
6. **Clean GitHub repo** — README, Dockerfile/environment.yml, CI running the benchmark
   suite on every commit (guideline §3, §6).
7. Optional stretch — upstream PR to GPTCache (guideline's "exceptional 100" path),
   attempted only after the above are solid; not a blocking deliverable.

## 7. Report story (the narrative, not just the checklist)

The report's throughline: *industry semantic caches all sit on one global threshold with
plain TTL and no cost model; we show that treating staleness as a correctness problem
(not a miss-rate problem) and eviction cost as a first-class signal, both learned
per-cluster, measurably improves cost-saved and stale-hit-rate without hurting hit-rate.*
Related work is framed with the same honesty as §3 (per-cluster threshold alone is not
novel; the calibration layer is) — that honesty is itself a clarity/correctness signal to
the grader, not a weakness to hide.

## 8. Open items before implementation starts

- Confirm arxiv metadata for arXiv:2603.03301 and arXiv:2607.04281 before final citation
  (flagged as date-inconsistent / very-recent by prior-art check).
- Read Category-Aware Semantic Caching (arXiv:2510.26835) in full before drafting related
  work — it is the umbrella threat to both C1 and C2.
- Pick the specific public secondary QA dataset (deferred to implementation phase — needs
  a quick look at what's already used in GPTCache's own benchmarks for comparability).
