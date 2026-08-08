# Related work

Reference notes for the report's Introduction and Discussion. arXiv IDs are kept exact
throughout.

## Biton & Friedman, "From Exact Hits to Close Enough" (arXiv:2603.03301, Feb 2026)

This is the closest prior art, and the work the ablation's substitute comparator stands in
for. The paper proves that optimal
offline semantic-cache eviction is NP-hard, supplies polynomial-time heuristics, and presents
online eviction policies that combine recency, frequency, and locality signals. It evaluates
these policies on GPTCache and releases its implementation, which is why GPTCache was chosen
as this project's baseline in the first place (see `docs/baseline-justification.md`).

Two findings from the paper directly shape the experiment design here. First, the authors
show that LRU is a poor eviction policy for most semantic caching workloads and that
frequency-based policies are strong baselines by comparison — which is why LFU-class
policies, not LRU, are treated as the floor for comparison in this project's ablation; an
improvement measured only against LRU would not be a result. Second, because their
implementation is released and targets GPTCache, GPTCache is the substrate on which their
policy could be run directly. It was never obtained here, so the eviction comparator is the
documented substitute in `gptcache_ext/eviction/baselines.py`, not their code, and no run
under `results/` exercises their policy.

The delta versus FreCoS: Biton & Friedman's policies combine recency, frequency, and
locality, all of which are access-pattern signals derived from how a cached entry has been
queried. FreCoS adds two signals that are orthogonal to access pattern — regeneration cost
and content validity over time — and evaluates against a correctness metric, stale-hit-rate,
that their setting does not define at all.

## Cortex (arXiv:2509.17360, September 2025)

Cited as an arXiv preprint: no peer-reviewed venue for it is corroborated, and the report's
bibliography carries it as a preprint accordingly. Cortex's eviction policy, LCFU, scores each
cache entry as `log(freq+1)·log(cost·10³+1)·log(lat+1)·log(staticity+1)/size`, combined with a
TTL-based purge. It is multiplicative, cost-aware, frequency-aware, staleness-aware, and size-
normalized — structurally the closest published eviction formula to FreCoS's value function.

The delta versus FreCoS is narrow and specific: Cortex's staleness term is a static
"staticity" score from 1 to 10, assigned by an LLM at write time, combined with a user-defined
TTL. FreCoS's staleness term is a decay rate learned per cluster from observed staleness in a
calibration split. The distinction is learned versus assigned, and the bracketing experiment
in this project (learned λ against a global-λ lower bound and an oracle-λ upper bound) is
designed specifically to test whether that learning does any measurable work. Cortex's LCFU
is not reimplemented as a comparator here: its formula incorporates remote-tool-call latency
metadata that has no equivalent in this project's setting, and a faithful port would be a
project of its own.

## GDSF (Cherkasova & Ciardo, HPCN 2001)

Greedy Dual-Size Frequency scores entries as cost times frequency divided by size, with a
global-clock aging term. It has no freshness semantics at all — its aging term ages access
recency, not content validity — so it establishes that cost- and size-aware eviction predates
this project by two decades, but it says nothing about staleness. FreCoS's contribution
relative to GDSF is entirely the staleness axis: the decay term learned from content validity,
absent from GDSF by construction.

## Category-Aware (arXiv:2510.26835)

This work assigns per-category TTLs to cached entries. The TTLs are load-based rather than
learned from observed staleness, and the work defines no stale-hit-rate metric or equivalent.
It is also the reason a third planned component of this project — calibrated per-cluster
similarity thresholds — was cut: that component would have been a lossy special case of
vCache's per-embedding threshold learning and is already covered in spirit by Category-Aware's
per-category treatment, so building and calibrating it would have cost more than it added.

## FreshCache (arXiv:2607.04281)

A RAG-specific per-tier probabilistic staleness gate. It shares FreCoS's lineage — both put a
staleness concept in the serve path rather than leaving it entirely to eviction — but the two
differ in kind, not just degree: FreshCache treats staleness as a probabilistic risk budget
per tier, while FreCoS uses a hard learned gate (serve or refuse) plus a named serving-
correctness metric, stale-hit-rate, that FreshCache's framing does not produce. FreshCache's
probabilistic-budget style is listed as grounded future work, as an alternative to FreCoS's
current hard gate.

## SCALM (arXiv:2406.00025)

Clusters cache entries and defines its own notion of per-cluster entry significance driving a
custom eviction strategy. The clustering step is structurally similar to FreCoS's k-means
cluster assignment, but SCALM's significance score is not staleness-aware and the paper does
not define or measure anything like stale-hit-rate. The overlap with FreCoS is limited to the
clustering mechanism, not the eviction or freshness logic built on top of it.

## MeanCache (arXiv:2403.02694)

Cost-motivated caching work, but eviction is explicitly not its contribution — its focus is
elsewhere in the caching pipeline. Included here for completeness of the cost-aware caching
literature; it does not compete with FreCoS's eviction value function or staleness gate.

## W-TinyLFU (TinyLFU: arXiv:1512.00727; shipped in Caffeine, Ristretto, Moka)

An admission-control policy, not an eviction policy: it decides whether a new entry is worth
admitting at all, using a frequency sketch, before eviction is ever invoked. It is explicitly
out of scope for this project — porting it would be an engineering exercise with no research
delta on the staleness or cost axes this project is about — and is listed as grounded future
work rather than a comparator, since adding admission control on top of FreCoS's eviction
and gate would be a separate axis of improvement, not a replacement for either.
