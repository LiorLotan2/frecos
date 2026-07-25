# FreCoS: Freshness- and Cost-Aware Semantic Cache — Design Spec

Status: DRAFT — awaiting user review
Date: 2026-07-25

"FreCoS" (Frequency-Cost-Freshness eviction) is a name coined for this project, not an
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

**Do not justify this as "maturity & community support."** GPTCache's last release is
v0.1.44 (Aug 2024), it carries 75 open issues / 16 open PRs, and the project README states
they no longer add support for new APIs or models — a grader can falsify "actively
maintained, mature community project" in under a minute, and that costs trust on the whole
report. The honest, and actually stronger, justification:

- **Frozen, stable API.** A library that isn't shipping breaking changes mid-project is a
  *better scientific control* than a moving target — nothing shifts under the extension
  between the start and end of the semester.
- **MIT license**, permissive enough for an academic fork.
- **Clean, verified seams.** Every integration point in §4 below is confirmed by direct
  source read, not by documentation (docs are stale given the maintenance state).
- **CPU-only, deterministic** — required for reproducibility (30% of grade); no GPU
  dependency to pin or vary across machines.

Baseline behavior (verified against GPTCache source):
- Single global `similarity_threshold` (default 0.8), `gptcache/config.py:40`.
- Hit decision: `adapter.py:98-107`, `adapter.py:173` (`if rank_threshold <= rank`).
- Eviction: count-based only (LRU/LFU/FIFO/RR), `gptcache/manager/eviction/memory_cache.py:43-59`.
  No metadata stored with evicted keys (`self._cache[obj] = True`). **Eviction decisions
  are made on number of entries, not bytes** — the project's own README flags this as
  causing inaccurate resource evaluation and potential OOM. This is a known, admitted gap,
  not a discovery.
- Timestamps (`create_on`, `last_access`) are stored but never read
  (`scalar_data/base.py:70-71`, `sql_storage.py:64-65`) — dead columns we repurpose.
- No admission control: every miss is inserted (`adapter.py:258-273`).
- No cost, no false-hit/stale-hit metrics — only op timers (`report.py`).

**Byte-size accounting is a plausible upstream contribution; a new eviction policy is not.**
A PR proposing a new policy into a repo with a 16-deep stale PR queue and a maintainer
statement of reduced scope will not land in a semester. Byte-size accounting is a
maintainer-acknowledged gap and a small, mechanical, reviewable change — the more credible
candidate if the upstream-PR path (§6, deliverable 7) is attempted at all. Neither path is
load-bearing for the grade; §6 keeps it as an optional stretch, not a dependency.

**Implication for §5.2's size sweep:** GPTCache has no byte accounting to sweep today.
Building it is itself scoped as the FreCoS eviction seam's prerequisite (`/size` in the
value function needs `size(entry)` to exist) — so the size sweep in §5.2 is only valid once
this is built, and is stated as such, not assumed to already work against stock GPTCache.

This becomes the one-page baseline-justification deliverable (§6 below), expanded from
this section.

## 3. Extension: 3 components, ranked by contribution

Prior-art check (adversarial, arxiv-verified) puts these at different novelty tiers.
Framing reflects that honestly — this is the actual claim-to-fame the report has to sell.

### 3.1 FreCoS — cost- and freshness-aware eviction (headline contribution)

```
value(entry) = log(freq(entry)+1) × log(regen_cost(entry)·10³+1) × freshness(age(entry), λ_cluster)
             / size(entry)
freshness(age, λ) = exp(-λ · age)
```

- `regen_cost` = `output_tokens × price_per_token` at write time (recorded, not estimated).
- `λ_cluster` learned per semantic cluster from observed staleness (cluster = k-means over
  cached-query embeddings, fixed at cache-build time — no online re-clustering, keeps this
  tractable and reproducible).
- `log(x+1)` on freq and cost: without it, a new entry (`freq=0`) scores 0 and is evicted
  immediately regardless of cost or freshness, and raw `regen_cost` is heavy-tailed enough
  to dominate frequency outright. Logging both puts them on comparable scales — this is a
  correctness fix, not a tuning choice, and must be unit-tested directly (assert a
  fresh-but-unaccessed high-cost entry outranks a stale low-cost one, and vice versa for a
  pathological case).
- `/size`: GDSF and LCFU (below) both divide by size because value-per-byte is the correct
  currency for a fixed-capacity cache — without it, FreCoS would retain one large answer
  over many small ones of equal total value. `/size` is ablated as its own row (§5.2), not
  assumed to help.
- Evict lowest `value(entry)`. Ties broken by oldest `create_on` (see C2 note on
  `create_on` vs `last_access` below — the same distinction applies here).

**Corrected novelty claim.** The original claim — "no existing policy fuses frequency ×
cost × freshness" — is false: **Asteria (arXiv:2509.17360)** already does this. Its LCFU
policy scores `log(freq+1) × log(cost·10³+1) × log(latency+1) × log(staticity+1) / size`
and evicts the lowest score, plus a separate TTL purge for anything past a user-set
threshold regardless of score. This is closely convergent with the form above — deliberately
kept convergent (see the log/size fixes above, adopted directly from Asteria's form rather
than reinvented) rather than claimed as independently derived.

The actual delta, stated precisely: Asteria's staleness term is an **LLM-assigned static
score (1–10)** plus a **user-set global TTL**; FreCoS's freshness term is a **λ learned per
semantic cluster from observed staleness in the traffic itself**, with no manual scoring
step and no single global TTL. The contribution is the learned, per-cluster freshness term
replacing a hand-assigned static one inside an otherwise-Asteria-shaped value function — a
narrow, real delta, not a new formula. Framed this way in the report; §3.1 does not claim
the fusion itself as novel.

Also nearest: GDSF (Cherkasova & Ciardo, HPCN 2001) — cost×frequency/size with global-clock
aging, no clustering, no learned staleness; the ancestor of the `/size` term. SCALM
(arXiv:2406.00025) — clusters query traffic and its abstract states it also covers eviction
strategy, not only admission; cited accordingly, not contrasted as admission-only. MeanCache
(arXiv:2403.02694) — cost-motivated, eviction is not its contribution.

**Ablation consequence:** the baseline for comparison cannot be LRU alone — LRU ignores
every signal FreCoS uses, so beating it is not evidence of anything. The ablation (§5.2)
adds a **cost-aware baseline** (GDSF, and/or a direct LCFU reimplementation) as the bar
FreCoS actually has to clear. Beating LRU is a sanity check, not a result.

**Scoping tradeoff, stated up front (not discovered later):** static clustering means
`λ_cluster`/`TTL_cluster` degrade under semantic drift (topics shifting over a run). This
is a deliberate reproducibility choice — dynamic re-clustering makes runs non-deterministic
and harder to reproduce (30% of grade), which outweighs the realism cost for this project's
scope. §5.2 adds a mis-specification experiment that measures this cost directly rather than
only confessing it; it is also stated in the report's Discussion and named as the lead
Future Work item (§7).

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

`age(entry)` is measured from `create_on` (content age), never `last_access` — the two are
not interchangeable, and using `last_access` would let a popular stale entry stay
permanently "fresh" simply because it keeps getting hit. This is stated explicitly because
it is exactly the kind of bug that passes unit tests (both fields exist, both are
timestamps) while silently invalidating every stale-hit-rate number. §4's unit tests must
assert the gate reads `create_on` specifically, with a test case where `last_access` is
recent but `create_on` is old and the gate still fires.

Nearest prior art: Category-Aware Semantic Caching (arXiv:2510.26835, Oct 2025) — per-
category TTLs, but load-based not learned-from-staleness, and reports no stale-hit-rate
metric. FreshCache (arXiv:2607.04281, 2026) — keeps GPTCache/SCALM's lookup machinery and
vCache's error-budget framing, adds a per-tier probabilistic staleness-risk gate, and
explicitly distinguishes itself from Category-Aware by *not* using a static per-category
TTL — meaning FreshCache's own related-work section already stakes out the ground between
this project and Category-Aware; read it in full before drafting related work (see §8),
not just cited at a distance. vCache (arXiv:2502.03771) — gates on semantic mismatch, not
temporal staleness. The remaining combination (learned per-cluster **hard** TTL gate, vs.
FreshCache's per-tier **probabilistic** gate, + named stale-hit-rate metric) is not
published as such — a narrower claim than the previous draft's "complementary axis."

**Interaction with FreCoS, predicted here before the ablation runs it:** if C2 hard-purges
everything past `TTL_cluster`, no cached entry FreCoS ever ranks is stale — the freshness
term in FreCoS's value function only ever discriminates among entries that already passed
C2's gate. Run with C2+FreCoS together, the freshness term should measurably compress
toward a narrow high range (most survivors are fresh by construction) and the ranking
should be driven more by `freq × cost / size`. Stating this now and confirming or falsifying
it in the ablation is stronger evidence of understanding the system than discovering it
after the fact.

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

`observed_optimal` and `n_cluster` are defined precisely, not left as a formula sketch:
- **Labels**: every candidate-hit pair `(query, cached_entry)` in the synthetic workload
  has a ground-truth same-answer label (known from the generator — a near-duplicate
  belongs to the same cluster and true answer by construction). This is the only source of
  labels; the calibration step is not run against the public secondary dataset, which has
  no such ground truth.
- **`observed_optimal`** = the similarity threshold that maximizes F1 (or minimizes
  false-hit-rate at a fixed recall target — pick one, state it, don't average both) over
  the labeled pairs observed so far *in that cluster*, via a small grid/ternary search over
  cosine similarity — not a closed form.
- **`n_cluster`** = count of labeled candidate-hit pairs observed for that cluster (pairs,
  not raw queries) — the quantity that actually determines how well-calibrated
  `observed_optimal` is.
- **`k`** (shrinkage strength) is swept as its own parameter (§5.2), not fixed by
  assumption — report the sensitivity, don't pick one value and hide the rest.

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
| C2 | serve | Insert staleness check at `adapter.py:173`, before returning a hit — reads `create_on` specifically (already stored, currently unused; see §3.2 on why not `last_access`). |
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

**Stretch — Wikipedia revision history as a third, externally-grounded staleness source**
(time permitting, not required): derive ground-truth "was this answer still valid at time
T" from real article edit timestamps, converting "all staleness results are self-generated"
from an objection that has to be argued away into a non-issue. Deferred to implementation
capacity, not a blocking requirement (§8).

### 5.2 Runs

**Baselines** (not just "vanilla GPTCache"): LRU (stock, the sanity check) **and** a
cost-aware baseline — GDSF and/or a direct LCFU reimplementation (§3.1) — since beating LRU
alone proves nothing (LRU ignores every signal FreCoS uses). FreCoS's claimed gain is
measured against the cost-aware baseline, not LRU.

**Statistical significance requires more than one seed.** A single fixed seed gives a
point estimate, not an interval — "statistically significant" (guideline §5, §7) is
unsupported without it. Every configuration below runs with **N≥10 seeds**, reported as
bootstrap confidence intervals or a Mann-Whitney U test between baseline and extension.

**Temporal train/test split, not fit-and-evaluate-on-the-same-data.** `λ_cluster` and
`TTL_cluster` are learned from observed staleness in the same synthetic trace that
stale-hit-rate is then measured against — fit and eval on the same segment is circular (the
system "predicts" what was programmed into the generator). Fix: fit on the first 30% of
each trace, evaluate stale-hit-rate and cost-saved only on the remaining 70%. Stated as a
methodology requirement, not left implicit.

**Bracketing runs**, to show the learned parameters are doing real work rather than
degenerate: a **λ-oracle** (perfect ground-truth knowledge, upper bound) and a **λ-global**
(single value fit across all clusters, lower bound). If learned-per-cluster-λ does not sit
meaningfully between them, the per-cluster learning step is not earning its complexity —
this needs to be known during implementation, not discovered while writing the report.

**Mis-specification experiment.** Inject semantic drift mid-trace (shift which cluster a
topic's queries map to) so the fixed clustering (§3.1's stated scoping tradeoff) is
measurably wrong, and report the resulting degradation in stale-hit-rate/cost-saved. This
turns the static-clustering limitation from a confessed weakness into a measured one.

**Parameter sweep:** cache size (50MB/100MB/200MB byte-based, contingent on the byte-size
accounting built per §2 — falls back to an equivalent entry-count sweep if that build slips,
and the report must say explicitly which was used), θ (per-cluster threshold prior), TTL
prior, cluster count K, shrinkage strength k (§3.3), and `/size` on vs. off (§3.1).

**Ablation:** baseline → +C1 → +C2 → +FreCoS, and each leave-one-out from the full stack,
plus the C2+FreCoS interaction check predicted in §3.2.

### 5.3 Metrics

hit-rate, false-hit-rate, stale-hit-rate, cost saved (regen-cost-weighted), latency
(mean/p95/p99), throughput, **memory and CPU utilization** (explicitly listed in the
guideline, previously omitted here), and **the extension's own per-request overhead**
(cluster lookup + threshold lookup + staleness check, measured in isolation) — a cost-aware
cache that adds meaningful latency to every request has to prove the savings exceed that
cost, not just report savings alone.

### 5.4 Correctness test oracle

"Cache behaves as expected" (guideline §7, 40% of grade) needs a concrete definition, not
just passing unit tests per component. Build a small reference implementation — plain dict
+ an explicit staleness table, no cleverness — and run it in lockstep with the real
implementation under the same seeded trace, asserting on every step: capacity is never
exceeded, eviction always picks true argmin of `value(entry)`, no entry is ever served past
its `TTL_cluster`, and same seed → byte-identical output across repeated runs. This lockstep
oracle is the artifact §6's "Extension code" deliverable actually has to ship, not an
afterthought to unit tests.

### 5.5 Execution model — subagents

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

**Lead with the metric, not the policy.** The headline claim is: *we introduce
stale-hit-rate as a first-class correctness metric for semantic caches, and show every
existing policy — including cost-aware ones like GDSF/LCFU — is blind to it.* This framing
is harder to prior-art away than an eviction-formula claim (§3.1 already shows why: the
formula itself has close prior art in Asteria), lands on the 40%-weighted correctness
criterion instead of the 15%-weighted performance one, and repositions FreCoS and C1 as
*mechanisms that move the metric* rather than things that must individually be defended as
novel inventions. C2 (the metric + the gate) leads the report; FreCoS and C1 follow as the
system built to act on what the metric reveals.

Full throughline: *industry semantic caches (and cost-aware academic ones) have no notion
of whether a hit is still correct, only whether it's a hit; we show that treating staleness
as a correctness failure, not a miss-rate statistic, and gating on a per-cluster learned TTL
rather than a global one, changes what gets measured and what gets evicted — and that a
learned-per-cluster freshness term inside an Asteria-shaped eviction value function
(FreCoS) captures savings a static staleness score cannot.* Related work is framed with the
same honesty as §3 throughout (per-cluster threshold alone is not novel, the calibration
layer is; the eviction formula is convergent with Asteria, the learned term is the delta)
— that honesty is itself a clarity/correctness signal to the grader, not a weakness to hide.

## 8. Open items before implementation starts

- Confirm arxiv metadata for arXiv:2603.03301 and arXiv:2607.04281 before final citation
  (flagged as date-inconsistent / very-recent by prior-art check) — external review found
  both resolve and are citable as-is; re-verify at submission time regardless, since dates
  this recent can still change.
- Read Category-Aware Semantic Caching (arXiv:2510.26835, umbrella threat to C1/C2) **and**
  FreshCache (arXiv:2607.04281, whose own related-work section already stakes out the
  ground between this project and Category-Aware) in full before drafting related work —
  not cited at a distance.
- Read Asteria (arXiv:2509.17360) in full before finalizing §3.1's related-work text — the
  LCFU policy it describes is the nearest prior art to FreCoS's value function and the
  claim must be scoped to the learned-per-cluster-freshness delta, not the fusion itself.
- Pick the specific public secondary QA dataset (deferred to implementation phase — needs
  a quick look at what's already used in GPTCache's own benchmarks for comparability).
- Decide whether the Wikipedia-revision-history stretch workload (§5.1) fits in the
  implementation timeline; if not, state its omission in the report rather than silently
  dropping it.
