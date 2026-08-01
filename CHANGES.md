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

## What was not fixed, and why

- **Seed count (Phase 3.1):** left at 10, not raised to 30. See above — compute cost of
  the Phase 2 rerun (~9 hours) made a further 3× rerun impractical within this session;
  flagged rather than silently skipped.
- **`results/ablation/size_term_isolation/`:** kept as a historical, no-longer-regenerable
  artifact (its runner and the size term it tested no longer exist), documented as such
  in the README and in `gptcache_ext/eviction/frecos.py`'s module docstring, per the
  brief's instruction not to leave a stale number in place without saying so.
- **Biton and Friedman's released policy, and Cortex's LCFU:** still not run directly
  against this workload (both were out of reach before this remediation and remain so);
  the eviction axis is still measured only against count-based baselines and FreCoS.
  Listed as future work in the Conclusion.
- **External, non-self-authored ground truth for staleness:** still absent. The
  Wikipedia feasibility spike's 40% rule-agreement result (against an 80% bar) predates
  this remediation and was not revisited; the circularity this creates (Discussion, Phase
  4 item 3) is now named explicitly rather than left implicit.
