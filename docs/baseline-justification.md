# Baseline justification: GPTCache

## Why GPTCache

This project extends GPTCache rather than a more actively maintained semantic cache. The
case rests on architecture and control properties, not on community activity, and it is
worth stating that openly rather than dressing a frozen dependency up as momentum.

GPTCache's most recent release is v0.1.44 (Aug 2024), and the maintainers' own README notes
that support for new model and API integrations has stopped. Normally this would count
against a dependency. Here it is an advantage: a frozen API is a better scientific control
than a moving one. The baseline is vendored at a pinned commit, so every performance delta
reported in the results is attributable to the extension rather than to an upstream release
landing mid-project. Chasing an actively developed cache would have meant re-validating
baseline behavior against each new release.

The second reason is architectural fit, verified by reading the source rather than assumed
from documentation. Every component this project modifies (the similarity threshold check,
the hit/miss decision, the eviction policy registry) sits behind a registered, named
interface, with one exception. The extension is additive: a new `EvictionBase` subclass, an
additive metadata store beside `CacheData` rather than a subclass of it, and a serve-path gate
that plugs into one shared decision helper. The exception is eviction: `EvictionBase.get()` is
a hardcoded if/elif chain with no lookup table a caller can register into, so reaching the new
policy through GPTCache's own factory requires monkeypatching that one function
(`gptcache_ext/eviction/frecos.py`). Nothing vendored is edited.
Specific line references for these claims are collected in `docs/baseline-source-map.md`,
which re-verifies every claim against the pinned commit actually vendored in this repo, so
this document does not repeat unverified line numbers.

Third, GPTCache is the baseline the closest prior art already uses. Biton & Friedman ("From
Exact Hits to Close Enough," arXiv:2603.03301) evaluate their eviction policies on GPTCache,
so sharing that baseline means a comparison against their policy needs no reimplementation on
a different substrate. Their released code was never obtained for this project, so the
comparator actually measured is a documented substitute
(`gptcache_ext/eviction/baselines.py`); this reason is about the substrate, not about a
comparison that was run.

Fourth, GPTCache's default embedding backend (`paraphrase-albert-onnx`) runs CPU-only and
deterministically, which keeps every benchmark run reproducible without GPU dependence and
without nondeterminism from a hosted embedding API.

## GPTCache's features and default eviction policy

GPTCache sits in front of an LLM call and serves a cached response when an incoming query is
semantically close enough to a previously seen one, using a single global cosine similarity
threshold (default 0.8) rather than exact-match keys. Its eviction policies are purely
count-based: LRU, LFU, FIFO, or random replacement, selected by name at cache construction
time. None of them reads generation time, access recency, or regeneration cost as anything
more than the single counter each policy already tracks, and none retains any metadata on an
evicted entry: the eviction cache stores `{key: True}` and nothing else. `create_on` and
`last_access` timestamps are persisted per entry but are not read by any decision logic in
the adapter or the eviction policies; they exist as columns with no downstream consumer. There
is no admission control (every miss is written back), and no cost accounting, false-hit
tracking, or staleness tracking exists anywhere in the reporting layer, which only counts
per-stage operation timers. Full claim-by-claim verification, with source file and line
references against the pinned commit, is in `docs/baseline-source-map.md`.

## Why not vCache

vCache (arXiv:2502.03771, ICLR 2026) was considered and rejected as the baseline. Its
contribution is per-prompt similarity threshold learning, replacing GPTCache's single global
threshold with a threshold learned per cached embedding, and eviction is explicitly not its
focus. This project's contribution is a learned per-cluster staleness model consumed by both
a serving-time validity gate and an eviction value function; adopting vCache as the baseline
would mean building the staleness and eviction work on top of a system whose own novelty is
in a different part of the pipeline, diluting the comparison rather than sharpening it.
GPTCache's plain fixed-threshold matching combined with unmodified count-based eviction gives
a cleaner substrate for isolating what a staleness-aware gate and eviction term add.
