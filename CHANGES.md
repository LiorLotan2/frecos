# Changes made in this remediation pass

Summarized per phase of the remediation prompt. Every number below is quoted from a
committed `results/*/results.csv`, `summary.md`, or `report/report.tex`; nothing here is
invented or extrapolated.

## Phase 0 — Scaffolding cleanup

- Removed every `agent card` / `implementation-plan.md` / `A3`–`A10` identifier from
  `benchmarks/harness.py`, `benchmarks/smoke.py`, `benchmarks/runners/*.py`,
  `gptcache_ext/eviction/baselines.py`, `docs/w1-calibration.md`, `tests/*.py`, and every
  `results/*/summary.md`, replacing each with a self-contained description or a plain
  cross-reference to the actual experiment name.
- Retitled every `results/*/summary.md` heading (`# A9 ablation:` → `# Ablation:`, etc.).
- README's stub-lie about `make bench-smoke` and the `<!-- BENCHMARK:A7 -->` markers, and
  the LICENSE/NOTICE requirement, were already fixed in an earlier commit on this branch
  (`d7fa28c`) before this remediation started; verified, not re-done.
- Fixed the flake8 baseline that predated this remediation: an unused import in
  `analysis/fig3_ttl_tradeoff.py` and long hand-labeled strings in
  `workloads/w2_wikipedia/spike/hand_labels.py` (added a per-file flake8 ignore for the
  latter, matching the existing precedent for `contracts.py`).

No numbers moved in this phase; it touched only comments, docstrings, and file names.

## Phase 1 — Reproducibility

- Added `make experiments` (runs all seven runners in dependency order), `make exp-*` for
  each individually, `make figures`, and `make report` to the Makefile.
- Rewrote README's benchmark section into "Reproducing the report": a table mapping each
  experiment to its output CSV and the report table/figure it feeds, with measured (not
  guessed) wall-clock runtimes.
- Pinned every dependency to an exact version in `requirements.txt` (new) and
  `environment.yml`; fixed the bug where `make install` omitted `matplotlib`, verified
  against a fresh venv.
- Extended `Dockerfile` to install from `requirements.txt` and documented
  `docker run frecos make experiments` / `make figures`, keeping `CMD ["make", "verify"]`.
- Extended CI: lint now covers `benchmarks analysis workloads` in addition to
  `gptcache_ext tests`; added a `figures-consistency` job (regenerates all four PNGs from
  committed CSVs, fails the build on any diff — verified deterministic given a pinned
  matplotlib version) and an `experiment-smoke` job (2 seeds × 1000 queries, no network
  dependency, exercises the real experiment path on every commit).
- Added the three missing `results/*/summary.md` files
  (`brackets/misspecified`, `brackets/mixture`, `ablation/size_term_isolation`), derived
  directly from their committed CSVs.

No numbers moved in this phase; it added tooling and documentation only.

## Phase 2a/2b/2c/2d — Correctness

**2a (clustering) and 2b (semantic index):** implemented the preferred fix, not the
fallback. `gptcache_ext/staleness/embedder.py` wraps GPTCache's default ONNX model with
an on-disk cache keyed by text hash; `gptcache_ext/staleness/assign_real_clusters.py`
embeds every distinct query text, fits k-means on the calibration split, and assigns
every row to its nearest centroid, keeping the generator's true label as
`true_cluster_id` for an adjusted-Rand-index accuracy check (`cluster_ari`), never
consumed by the gate or eviction. `benchmarks/semantic_index.py` replaces exact-text-match
lookup with brute-force cosine similarity at GPTCache's default 0.8 threshold.

This is the most consequential change in the whole remediation. **Every reported number
in every experiment changed as a result**, and the direction of the report's central
finding reversed: under real clustering, `cluster_ari` is 0.02–0.06 (barely above what a
random assignment produces) across every bracket-style experiment, and learned no longer
tracks oracle — it tracks global. Root cause verified by direct inspection, not asserted:
the workload's canonical query template differs across clusters only in two embedded
numbers, and a real sentence embedder scores that difference at 0.6–0.9 cosine
similarity, well above the 0.8 threshold, which also means ~92–97% of served hits across
every experiment are false hits (previously an always-zero metric under exact-match).

**2c (GPTCache integration):** added `tests/test_gptcache_integration.py`, which builds a
real `gptcache.manager.data_manager.SSDataManager` (not `MapDataManager`, which never
calls `EvictionBase` at all), drives it through `register()`'s monkeypatched factory with
`policy="FRECOS"`, forces eviction, and asserts the victim matches
`FreCoSEviction.select_victim()` computed independently from the same metadata. Corrected
`gptcache_ext/eviction/frecos.py`'s module docstring, which claimed the policy is "a new
eviction subclass registered through the existing hook" — GPTCache's `EvictionBase.get()`
has no such hook; `register()` monkeypatches the classmethod because the factory is a
hardcoded if/elif chain with no lookup table.

**2d (size term):** chose option (ii) — removed `/size_bytes` from FreCoS's value
function (`gptcache_ext/eviction/frecos.py`) entirely, rather than implementing a
byte-budgeted eviction mode, since eviction here runs under an entry-count budget, which
gives size-normalization no economics to act through. Dropped ablation row 6 and its
runner (`benchmarks/runners/size_term_isolation.py`); the historical
`results/ablation/size_term_isolation/` stays committed as the empirical confirmation
that justified this choice, but is no longer regenerable by any command in this repo.

A data-integrity bug was found and fixed during verification, not left in the committed
data: `results/brackets/results.csv` briefly had a stale 31-column header (from before
`cluster_ari` was added to `CSV_COLUMNS`) sitting on top of 30 already-written
32-column data rows, left over from a `git checkout HEAD --` colliding with an in-flight
rerun's own write during Phase 2d. Caught by `csv.DictReader` putting the 32nd field
under a `None` key; fixed by keeping the new-schema rows and rewriting the header from
the current `CSV_COLUMNS`. Every other results file was checked and found consistent
before trusting any of them.

## Phase 3 — Strengthen the empirical claim

- **3.1 (seed count):** **not done.** Explicitly discussed and declined: the Phase 2
  rerun (real embedder + real clustering) alone took just under 9 hours end to end on the
  available machine, almost all of it one-time embedding cost. Raising seeds from 10 to
  30 would roughly triple that. Given the scale already reached, this was deferred rather
  than attempted; the seed count remains 10 throughout, and every p-value in this report
  is still subject to the coarser-than-it-looks caveat that implies.
- **3.2 (multiple-comparison correction):** done. `analysis/multiple_comparisons.py`
  implements Holm-Bonferroni (hand-rolled, scipy unavailable), with two primary
  comparisons designated up front (learned vs. global; gate-on vs. LFU floor) and every
  other Mann-Whitney test treated as secondary. Applied to the actual rerun's p-values;
  every previously-significant result stays significant after correction (largest
  adjusted $p \approx 0.023$).
- **3.3 (fair eviction test):** done, and found a real bug in the first attempt.
  `benchmarks/runners/cost_aware_eviction.py` (gate off, heterogeneous cost, scored on
  `cost_saved_usd`) first ran at `cache_size_entries=1650` (matching the main ablation)
  and produced byte-identical results across FreCoS/LFU/LRU — traced to the cache never
  filling under the real semantic index's high hit rate (339–372 misses per run, under
  budget), so eviction never ran at all. Fixed by measuring the trace's actual working
  set with an unlimited cache (339–474 distinct entries needed) and rerunning at
  `cache_size_entries=100`. The fixed run shows a real, significant effect: FreCoS beats
  LFU on cost saved ($p \approx 0.0009$, $r \approx 0.74$), LRU maximizes cost saved but
  at more than double FreCoS's stale-hit-rate.
- **3.4 (environment capture):** done. `benchmarks/capture_env.py` writes `env.json`
  (CPU model, core counts, RAM, OS, kernel, Python version) next to every experiment's
  `results.csv`; wired into all seven runners. One gap: `results/brackets/` has no
  `env.json` from the runner itself, since that process had already loaded the
  pre-`capture_env` version of `main()` when the wiring landed mid-rerun; generated
  manually afterward from the same machine, so the fact recorded is accurate, just not
  produced by the runner in that one case.

## Phase 4 — Report revision

- Abstract and Introduction rewritten to lead with the clustering-quality finding, not
  the disowned 19× floor comparison from the pre-remediation report.
- Every results table and figure in Section 5 regenerated from the Phase 2/3 rerun.
  Bracketing, its calibration-sparse follow-up, and both misspecification checks
  (Weibull, adversarial mixture) all show the identical reversed pattern.
- Ablation cut from six rows to five (size-term row gone); the new byte-identical-rows
  finding in rows 1–3 traced to the same cache-sizing artifact fixed in the new
  cost-aware-eviction subsection, not left unexplained.
- New `ssec:costaware` subsection reports the fixed fair test of FreCoS's cost term.
- `useful-hit-rate` redefined as a per-hit fraction rather than a fraction of all scored
  queries: the old definition can go negative once false-hit-rate is large (it was always
  zero before real clustering/semantic index existed to make it non-zero).
- Named the stale-hit-rate/oracle-ceiling circularity as an explicit limitation
  (Discussion), per the remediation brief's Phase 4 item 3.
- Bibliography: fixed 3 factual errors found by independently re-verifying all 11
  references against arXiv/GitHub directly (not from memory): `bitonfriedman2026`'s title
  and first author name were wrong; `cortex2026`'s year was wrong (arXiv ID `2509.17360`
  is September 2025, not 2026 — the exact bug the brief flagged) and it also carried two
  unverifiable claims ("NSDI 2026", "earlier preprint: Asteria") that no source
  corroborated, removed; `tinylfu2015` was missing its third author. Converted all
  bracket-style `[1]`–`[11]` citations to `\cite{}`; deleted the unused
  `report/references.bib` since `thebibliography` (not BibTeX) is what's kept.
- Figure/file naming fixed to match presentation order:
  `fig2_brackets.png` → `fig1_brackets.png` (was rendering as Figure 1, named fig2),
  `fig1_ablation_stale_hit_rate.png` → `fig2_ablation_stale_hit_rate.png`,
  `fig4_cache_size_knee.png` → `fig3_cache_size_knee.png`,
  `fig3_ttl_confidence_tradeoff.png` → `fig4_ttl_confidence_tradeoff.png`. Analysis
  scripts renamed to match (`analysis/fig1_brackets.py` etc.); `make_figures.py` updated.
- Latency-figure omission (guideline §5 asks for one by name) now stated explicitly in
  text, with the reason: miss latency is a seeded log-normal placeholder, so its
  distribution plot would show a random-number generator's shape, not any real system's.
- Appendix A gained the real GPTCache integration test as a fourth correctness level;
  Appendix B's artifact table updated with every file this remediation added.
- **Page count: not fully met.** The brief caps the body at 12 pages; after extensive
  compression (Related Work, Baseline, Design, Metrics, Ablation, Discussion, and
  Conclusion all tightened; several redundant cross-reference paragraphs deleted
  outright; two tables merged into one; figure float placement changed from `[!ht]` to
  `[H]` to eliminate whitespace from float drift), the body settled at approximately
  13.2 pages and further cuts stopped reducing the page count at all. Accepted rather
  than cutting into content that supports the report's correctness claims — this
  revision's whole point is the added clustering-quality and cost-aware-eviction
  material, and further compression risked losing the reasoning that makes those
  findings verifiable rather than asserted.

## Phase 5 — Second-review remediation

- **Cost-aware eviction table/prose (Table `tab:costaware`) inverted its own finding:**
  the caption and prose claimed FreCoS "beats LRU substantially on stale-hit-rate" and
  that LRU "pays for its cost advantage with the highest stale-hit-rate"; the table
  directly above states the opposite (LRU: 0.227, FreCoS: 0.491, LFU: 0.677 -- lower is
  better) with no per-seed overlap between LRU and FreCoS. Fixed everywhere this appeared
  (abstract, Section 5.3, Discussion, Conclusion): LRU strictly dominates FreCoS on this
  test (more cost saved, fewer stale hits), because recency of access happens to track
  recency of write on this trace, so LRU gets a freshness benefit for free with no
  staleness model at all. FreCoS still beats the LFU floor on cost saved with a large
  effect; that claim was correct and is unchanged.
- **Clustering result reframed as a diagnosed measurement failure, not a negative
  result:** the abstract, Introduction contribution #2, Discussion, and Conclusion
  presented "per-cluster staleness learning does not beat pooling" as a finding. Root
  cause (verified in `workloads/w1_synthetic/generator.py:213`): every canonical query
  text differs across clusters only in two embedded integers, so a sentence embedder
  cannot recover cluster identity from it at all (ARI 0.02--0.06, at random-assignment
  level). The per-cluster learning this project set out to test was never actually
  exercised under real clustering -- there were no real clusters to learn from -- so
  "learned tracks global" measures the absence of clusters, not the value of per-cluster
  learning. Reworded every instance to say this explicitly.
- **`cost_saved_usd` noted as excluding stale hits but not false hits:** at this
  workload's false-hit-rate (~92--97%), the reported cost-saved numbers are dominated by
  hits that returned the wrong answer. Stated explicitly at the point of the claim
  (Section 4) rather than silently left implied by the stale-hit-only exclusion. The
  metric fix (also exclude `is_false_hit`) and the generator text fix (distinct topic
  and entity phrases per cluster/answer, replacing the two-digit template) are both fully
  specified but **not applied**: applying either would change every committed
  `results/*/results.csv`, and rerunning the full suite is a multi-hour cost this pass
  did not have room for (see Phase 3.1 above for the same constraint). Applying and
  rerunning both together is the single highest-value next step, named as such in the
  Conclusion.
- **`make report`:** the Makefile's `report` target now calls `tectonic`, not
  `pdflatex` (not installed in the environment this remediation ran in). Verified to
  compile `report.tex` to a 16-page PDF with only benign Overfull/Underfull hbox
  warnings. (Superseded by Phase 6 below: the report is now 12 pages.)

## Phase 6 — CI failures, a real data error, and the page-count overshoot

Follow-up pass, triggered by a review of this branch's own CI runs and report content
against the grading rubric. Everything below was verified directly, not asserted.

- **`figures-consistency` CI job (root-caused, not just retried):** two independent,
  deterministic causes, both confirmed by installing the exact pinned dependency
  versions in a clean venv and rerunning `make figures`.
  1. The four committed PNGs were rendered with `matplotlib==3.11.1` (visible in each
     PNG's own metadata), but `requirements.txt` pins `3.10.9` — the version CI
     actually installs. Regenerating with the pinned version always produces a
     pixel-different PNG. Fixed by regenerating and committing the PNGs under the
     pinned version, so `make figures` is now idempotent against a clean install.
  2. `analysis/make_supplementary.py` wrote `supplementary.csv` via `csv.writer`
     without `lineterminator="\n"`, so it always emits `\r\n` regardless of platform,
     while the committed file has plain `\n`. Fixed by passing
     `lineterminator="\n"` explicitly; the CSV's actual values were already correct,
     only the line endings were wrong.

  Both bugs were platform-independent and would have failed on every future CI run and
  every reviewer's clean clone, not just intermittently.
- **Data error in `results/cost_aware_eviction/summary.md`:** the Results table listed
  FreCoS's median `cost_saved_usd` as `7.08`, contradicting both this same file's own
  prose two paragraphs above it (`11.83`) and the number in `report/report.tex` Table
  `tab:costaware` (`11.83`, correct). Recomputing directly from
  `results/cost_aware_eviction/results.csv` confirms `11.83` (95% CI `9.17, 13.46`) is
  right; fixed the table. All nine other `summary.md` files were checked the same way
  and found consistent with their CSVs — this was an isolated transcription error, not
  a pattern.
- **Report page count (12 pages, not 16):** the previous pass left the report at 16
  pages against the 8--12 page guideline, worse than its own claim of "~13.2 pages."
  Fixed by: dropping the font from 11pt to 10pt (still within the guideline's ≥10pt
  floor); placing Figures 3 and 4 side by side in one float instead of stacked;
  tightening the Discussion/Conclusion overlap, which restated the same three findings
  twice; removing an unused bibliography entry (`squad2018`, never cited in the body);
  and tightening bibliography item spacing. No table, figure, or number was cut.

## Phase 7 — Fixing the workload itself, and a third-review pass

Triggered by a third external review of this branch. That review's central point:
Phase 5's "diagnosed measurement failure" framing was honest but left the project's
central mechanism (per-cluster staleness learning) never actually tested — the highest
remaining value in the whole remediation was applying the generator fix already
specified in Phase 5/6 and rerunning, not writing around it again. Everything below
was verified directly (tests run, stats independently recomputed, figures regenerated
and diffed), not asserted.

- **P0 — fixed the generator text and reran every experiment.**
  `workloads/w1_synthetic/generator.py`'s canonical query template
  (`f"What is the current status of topic {cluster_id}-{answer_id}?"`) differed across
  clusters only in two embedded integers, which no general-purpose embedder could use
  to recover cluster identity (median `cluster_ari` 0.036 across every prior
  experiment). Replaced with `CLUSTER_TOPICS` (51 distinct real-world subjects, one per
  cluster, cycled past index 50) crossed with `ANSWER_ASPECTS` x `ANSWER_QUALIFIERS`
  (25 x 30 = 750 combinations per cluster), keyed by each canonical answer's position
  *within its own cluster* (not the global `answer_id`, whose stride mod `n_clusters`
  would alias back onto the same vocabulary slot far sooner than the vocabulary itself
  repeats). Verified empirically, not just by construction: `cluster_ari = 0.52` at
  `n_queries=3000, seed=0` against the real ONNX embedder, and zero duplicate canonical
  texts across 1650 answers at that scale. Added
  `tests/test_w1.py::test_canonical_query_text_is_cluster_separable_under_a_real_embedder`,
  asserting `cluster_ari > 0.5` on this exact configuration as a permanent regression
  guard — this test downloads and runs the real ONNX embedder (network required on
  first run, cached under `/tmp` after), the same requirement `benchmarks.
  experiment_smoke` already has.

  Reran all seven experiments behind Section 5, at 3,000 queries and 5 seeds instead of
  12,000 and 10 (the brief's own suggested trade against the ~9-hour full-scale cost,
  since the fix's thesis-level conclusion does not depend on trace size). Cache sizes,
  where the original design chose them as a percentage of the answer-id working set,
  were recomputed proportionally at the new scale (e.g. 412 = round(1650 * 0.25) for
  brackets/ablation, replacing 1650 = round(6600 * 0.25); the cost-aware-eviction
  experiment's cache size was re-derived empirically the same way the original did,
  confirming 25 entries forces real eviction pressure at this scale). Median
  `cluster_ari` across the rerun is 0.40--0.45, and the report's central finding
  reverses again, this time correctly: learned beats global with a large, significant
  effect ($r \approx -0.84$, $p \approx 0.028$ on the main bracket), and separates
  significantly from oracle in the expected direction ($r \approx 0.92$) — the shape the
  pre-Phase-2 report originally claimed, now backed by a workload a real embedder can
  actually separate. `false_hit_rate` drops from ~0.97 to ~0.90--0.91, not eliminated:
  direct inspection shows the residual is now same-cluster, different-aspect query
  pairs (e.g. two distinct Renaissance-art questions) scoring 0.7--0.8 cosine
  similarity, close to the SemanticIndex's 0.8 threshold — a more defensible failure
  mode than the old cross-cluster conflation, but still a first-order caveat on every
  number in Section 5.

- **P0 — `benchmarks/experiment_smoke.py` now exercises the real path.** It called
  `run_harness(...)` with no `index=`, silently defaulting to `ExactMatchIndex` and the
  generator's oracle `cluster_id` — the ~1% exact-match hit-rate regime, never the real
  50--95% band every committed result actually runs in. Now passes a real
  `benchmarks.semantic_index.SemanticIndex` and `benchmarks.embedding_pipeline.
  prepare_trace` (real k-means over embeddings), and asserts `hit_rate >= 0.20` to make
  a silent fallback to the exact-match regime fail loudly rather than pass green.

- **P1 — `analysis/fig3_cache_size.py`'s knee is now computed, not hardcoded.** The
  module had `KNEE_SIZE = 1980` / "30% of working set" left over from before a rerun
  had already moved the true knee to 990 / 15% — exactly the class of bug the module's
  own docstring claimed was swept. Replaced with `find_knee()`, which reads the knee
  directly off the same `results.csv` the plot itself renders (smallest cache size
  whose median hit_rate is within 1% of every larger size's), so the annotation cannot
  drift out of sync with the data again. At the new 3,000-query scale this computes
  248 entries = 15% of the 1650-entry working set — the same proportion the pre-fix
  15%-knee finding reported, a useful cross-check that the knee is a property of the
  workload's answer-diversity structure, not of trace size.

- **P1 — rank-biserial correlation, fixed and made regenerable.** `results/brackets/
  summary.md` (and every effect size quoted from it in `report.tex`) defined
  "rank-biserial r" as `|z|/sqrt(n1+n2)`, a different, z-based rank correlation, not
  rank-biserial correlation (`r = 2*U_a/(n1*n2) - 1`), and discarding the sign of `z`
  meant every effect size lost its direction. There was no committed script computing
  either value — every prior U/p/r triple in this project was computed by hand and
  re-typed, with nothing to rerun. Added `analysis/stats.py`
  (`mann_whitney_u`, hand-rolled: scipy unavailable in this sandbox, same reason
  `analysis/multiple_comparisons.py` and `gptcache_ext/staleness/cluster_accuracy.py`
  hand-roll their own statistics), unit-tested against closed-form cases in
  `tests/test_stats.py` (complete separation gives `r = ±1`; identical samples give
  `r = 0`; ties handled via average-rank), and independently verified against this
  project's own pre-fix committed data before trusting it for the rerun's numbers: for
  `learned-vs-oracle` on the pre-fix `results/brackets/results.csv`, it recovers
  `U=96.0`, `p≈0.0005` exactly, and `r=0.92` — matching the value flagged as correct by
  the review that triggered this phase (report previously stated `r=0.78`). Every
  rank-biserial number quoted in the rewritten `report.tex` and `results/*/summary.md`
  now comes from this module.

- **P1 — `useful_hit_rate` counted directly, not reconstructed.**
  `analysis/fig4_ttl_tradeoff.py` computed `useful_fraction_of_hits` as
  `n_hits - n_stale_hits_served - n_false_hits`, then clamped the result at
  `max(..., 0)`. Root cause: `is_stale_hit` and `is_false_hit`
  (`benchmarks/metrics.py`) are independent, overlapping predicates — a hit can be both
  — so that subtraction double-counts the overlap and can go negative once both rates
  are large, and the clamp made a genuinely floored value read as a measured zero.
  Added `is_useful_hit` (a hit that is neither stale nor false) and `useful_hit_rate`
  to `benchmarks/metrics.py`, wired `n_useful_hits`/`useful_hit_rate` into
  `benchmarks.harness.CSV_COLUMNS` and every runner's output, and rewrote
  `fig4_ttl_tradeoff.py` to read the column directly, removing the clamp entirely (it
  is structurally unnecessary once the count is direct, not reconstructed). Added
  hand-worked fixture tests in `tests/test_metrics.py`, including a case with a single
  hit that is both stale and false, which the old formula would score as -1 and this
  one correctly scores as 0. At the new scale, useful_hit_rate is a genuine,
  non-clamped, monotonically-rising curve (0.04 at TTL confidence 0.80 to 0.46 at
  0.99) — a different, more informative story than the pre-fix rerun's "zero through
  confidence 0.90" finding, itself an artifact of false-hit-rate swamping the metric
  before the generator fix.

- **P1 — deleted `docs/report.md`.** 620 lines of the disowned pre-remediation report
  ("roughly 15 times," "tracks an oracle rate closely," a six-row ablation), in the
  same first-person voice as the current report, with no superseded banner and no
  incoming references from any other committed file. `report/report.pdf` is the only
  report artifact now.

- **P1 — deleted the stale `phase-5/a12-report` branch from GitHub** (`origin/
  phase-5/a12-report`, unrelated history to `main`/`main-reconciled`, carrying the old
  15-page pre-remediation report). Left the equivalent local checkout untouched per
  explicit instruction; only the remote ref was removed.

- **P2 — documented the Python 3.10+ requirement.** `requirements.txt` pins
  `numpy==2.2.6`, which has no wheels for Python <3.10; on a stock macOS `python3`
  (verified against the system's actual 3.9.6), `pip install -r requirements.txt`
  fails with a resolver error that never names numpy as the cause. Added a version
  guard to `make install` (fails fast with an explicit message naming the actual
  interpreter and version found, and how to point `PYTHON` at a newer one) and a README
  note under Install. Verified the guard actually rejects Python 3.9.6 and accepts
  3.13.

- **P2 — documented `make figures`'s platform dependence.** The `figures-consistency`
  CI job only passes on the Linux runner: regenerating on macOS, even with the exact
  pinned `matplotlib` version, produces byte-different PNGs from the committed
  Linux-rendered ones (font rasterization differs by platform) — verified directly by
  running `make figures` on this machine and diffing. `analysis/figures/
  supplementary.csv`, by contrast, reproduces byte-identically on macOS too, since it
  has no font rendering involved; the README now states both facts side by side next
  to the existing matplotlib-version warning, naming the stronger claim as stronger
  rather than leaving the platform gap implicit.

- **Not touched, and why:** the README's advertised runtimes for `make experiments`
  (~9 hours cold-cache, dominated by embedding) were not independently re-timed against
  a fully empty `.embedding_cache/`; every experiment in this rerun ran against the
  same seven runners at reduced scale, and the surrounding pass had no room for a
  second from-scratch full-scale timing run on top of the P0 rerun itself. Flagging
  this as unverified rather than silently claiming it is now accurate at either scale.

## Phase 8 — Report polish, then the five known code defects

Two passes on the `phase-8/report-polish` branch. The first rewrote the report for a
final-version voice (no meta-commentary about earlier drafts, 12 pages including the
appendix, a general abstract, no section-roadmap paragraph) and stopped labelling the
harness's gate-off eviction baseline "LRU" when it was really insertion order. The second
fixed the defects that label was working around, which invalidated the committed numbers
and forced another rerun.

- **`bump_freq` now advances `last_access`.** `benchmarks/harness.py`'s
  `ExactMatchIndex.bump_freq` incremented `freq` but left `last_access` at its insertion
  value, so the LRU policy was really FIFO and the report had to say so. It now sets
  `last_access = now` and leaves `create_on` alone, which is what the staleness invariant
  requires (`tests/invariants.py` checks that staleness decisions read creation time and
  never last-access time). `benchmarks/semantic_index.py` inherits the fixed method. The
  ablation's rows 1--3 still tie seed by seed, for the reason the report already gives:
  at a 412-entry budget with 178--210 misses per run, eviction never fires, so no policy
  is ever called to pick a victim.

- **`peak_rss_mb` is now a real peak.** It was a single `memory_info().rss` reading taken
  after the replay finished. `_replay` now samples RSS every 100 scored queries
  (`RSS_SAMPLE_EVERY`) and keeps the maximum, sampling outside the `perf_counter` region
  around `decide()` so it never lands in the measured overhead. The reported values fell
  (206.1 MB to 179--184 MB) because the old post-replay reading included allocations the
  replay itself had already released.

- **`INDEX_THRESHOLD` renamed and documented.** It was named as if it were a semantic
  similarity threshold, but it is only ever passed alongside `ExactMatchIndex`, whose
  `search()` returns a fixed match rank or `None`. Renamed to `EXACT_MATCH_THRESHOLD`,
  with `INDEX_MATCH_RANK` next to it and a comment stating that every runner behind the
  report passes `benchmarks.embedding_pipeline.SEMANTIC_THRESHOLD` (0.8) explicitly
  instead.

- **`cost_saved_usd` now excludes false hits, not just stale ones.** The metric change
  specified in Phase 5 and deferred in Phase 7 is applied: it sums `regen_cost` over
  `is_useful_hit(r)` rows only. At this workload's ~0.90 false-hit-rate that drops every
  absolute cost value roughly tenfold, which is the point: the old number was an upper
  bound, not a measurement. `tests/test_metrics.py` gains
  `test_cost_saved_excludes_false_hits_as_well_as_stale_ones` and its existing derivation
  expectation moves 0.10 to 0.08.

- **Figure fonts are legible at the size the report renders them.** `analysis/common.py`
  used a 7-inch source width for figures typeset into a 3.9-inch or 3.0-inch slot, which
  scaled 11pt type down to under 5pt on the page. Source dimensions are now chosen so
  each figure lands near 1:1 at its intended width (`FIG_WIDTH`/`FIG_HEIGHT` for the
  0.62\textwidth figures, `FIG_WIDTH_SMALL`/`FIG_HEIGHT_SMALL` for the minipage pair),
  putting displayed labels at about 10.4pt against the report's 11pt body. Three follow-on
  defects surfaced once the type was large enough to read: fig2's y-axis label overflowed
  the canvas and rendered as "95% C" (fixed by giving that one figure more height, since
  its rotated row labels eat into the axes), fig3's knee annotation ran past the right
  spine and sat on the plateau line (now placed in axes-fraction coordinates and
  shortened, with the caption carrying the full sentence), and fig4's lower panel was
  labelled `useful-fraction-of-hits` while the report, the CSV column and
  `benchmarks/metrics.py` all call it useful-hit-rate (now consistent). Figures were
  regenerated inside the Linux container, keeping them byte-consistent with what CI's
  `figures-consistency` job produces.

- **Rerun and renumbered.** Fixes 1 and 4 change committed results, so every experiment
  behind Section 5 was rerun at the same 3,000 queries and 5 seeds, on the same Python
  3.13 environment recorded in `results/brackets/env.json`. Reproducibility was checked
  before trusting the rest: the brackets global seed-0 run reproduced its committed
  `n_hits` and `stale_hit_rate` exactly, with only `cost_saved_usd` moving. Every
  stale-hit-rate, hit-rate, false-hit-rate, useful-hit-rate and `cluster_ari` number in
  the report is unchanged; the cost columns, the latency/resource table, and the
  cost-aware eviction section are not.

- **The cost-aware eviction result flipped, and the report now says so.** With false hits
  excluded, FreCoS versus LFU on cost saved goes from `U_a=21.0, p ~ 0.076, r ~ 0.68` to
  `U_a=13.0, p ~ 0.917, r ~ 0.04`: no effect. Real LRU beats FreCoS on cost saved
  (`U_a=5.0, p ~ 0.117, r ~ -0.60`) and separates perfectly from it on stale-hit-rate
  (`U_a=25.0, p ~ 0.009, r ~ 1.00`), and separates perfectly from LFU too
  (`U_a=0.0, p ~ 0.009, r ~ -1.00`). The abstract, contribution 3, Section 5.3, the
  Discussion and the Conclusion now report cost-aware eviction as a negative result
  rather than a narrow win, and trace the mechanism to creation age tracking access
  recency on this trace.

- **Verified, not asserted:** 96/96 tests pass, `flake8` is clean over `gptcache_ext
  tests benchmarks analysis workloads`, the report builds with zero overfull hboxes, and
  the PDF page-tree `/Count` is 12.

## What was not fixed, and why

- **Seed count:** every experiment in this rerun uses 5 seeds, not the original design's
  10 (Phase 7's own scale reduction) nor the never-attempted 30 (Phase 3.1). Compute
  cost of a from-scratch embedding-bound rerun at 12,000 queries and 10 seeds is still
  roughly 9 hours; flagged in the report's Discussion and Conclusion as a named
  statistical-power cost, not silently absorbed into the reported numbers.
- **`results/ablation/size_term_isolation/`:** still kept as a historical,
  no-longer-regenerable artifact, unchanged from Phase 2d. Its `cost_saved_usd` column
  predates the Phase 8 metric change and its summary now says so; the conclusion it
  supports rests on stale-hit-rate and hit-rate, which the change does not touch.
- **Biton and Friedman's released policy, and Cortex's LCFU:** still not run directly
  against this workload; the eviction axis is still measured only against count-based
  baselines and FreCoS. Listed as future work in the Conclusion.
- **External, non-self-authored ground truth for staleness:** still absent, unchanged
  from Phase 4/5.
- **README's ~9-hour cold-cache runtime claim for `make experiments`:** not re-timed
  against an empty embedding cache in this pass (see above).
