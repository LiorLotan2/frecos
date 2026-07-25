"""Oracle and pipeline must agree on decisions across a 5,000-query stub trace.

The oracle (tests/oracle/reference_cache.py) checks staleness against the true
valid_until on each entry. To make the real pipeline's gate comparable rather than a
different question entirely, this test gives the gate the entry's true valid_until too
(a stub, only-for-this-test gate, not the learned TTLGate that A3 owns) so both sides are
answering "is this entry still valid at now", just through different code paths.
"""
import random
from dataclasses import dataclass
from typing import Optional

from gptcache_ext.contracts import Decision, EntryMeta
from gptcache_ext.pipeline import decide
from tests.oracle.reference_cache import ReferenceCache, cosine_similarity

N_QUERIES = 5_000
N_DISTINCT_ANSWERS = 150
EMBEDDING_DIM = 8
THRESHOLD = 0.999


class TrueValidityGate:
    """Test-only gate exposing the oracle's own ground truth through the Gate protocol,
    so decide() and the oracle are asked the same staleness question."""

    def __init__(self, valid_until_by_entry):
        self._valid_until = valid_until_by_entry

    def is_stale(self, meta: EntryMeta, now: float) -> bool:
        return now > self._valid_until[meta.entry_id]


@dataclass
class Candidate:
    rank: float
    meta: EntryMeta


class LinearScanIndex:
    """Same nearest-neighbour rule as the oracle (tests/oracle/reference_cache.py):
    a query without an exact prior match still finds the closest entry by cosine
    similarity, and it is the threshold check, not the lookup itself, that turns that
    into a miss. An exact-match dict index would answer a different question here
    (present or absent) instead of the one decide() is built to ask (close enough or
    not), so it can't be swapped in without changing what "agreement" means.
    No eviction: this test is about gate agreement, not eviction agreement, so both
    sides keep every entry inserted.
    """

    def __init__(self):
        self._entries = []  # list of (embedding, meta)

    def insert(self, embedding, meta):
        self._entries.append((embedding, meta))

    def search(self, embedding) -> Optional[Candidate]:
        best_meta = None
        best_score = float("-inf")
        for stored_embedding, meta in self._entries:
            score = cosine_similarity(list(embedding), list(stored_embedding))
            if score > best_score:
                best_score = score
                best_meta = meta
        if best_meta is None:
            return None
        return Candidate(rank=best_score, meta=best_meta)


def make_embedding(token: int):
    # One-hot-ish embedding keyed by token id, distinct tokens are orthogonal so
    # cosine similarity is exactly 1.0 for a repeat and 0.0 otherwise. That keeps the
    # threshold check trivial and puts the entire test weight on the staleness gate.
    vec = [0.0] * EMBEDDING_DIM
    vec[token % EMBEDDING_DIM] += 1.0
    vec[(token * 7 + 3) % EMBEDDING_DIM] += 1.0
    return tuple(vec)


def build_trace(n, n_answers, seed):
    rng = random.Random(seed)
    trace = []
    t = 0.0
    for _ in range(n):
        t += rng.uniform(0.5, 2.0)
        answer_id = rng.randrange(n_answers)
        half_life = 50.0 + (answer_id % 10) * 20.0
        valid_until = t + rng.expovariate(1.0 / half_life)
        trace.append({"t": t, "answer_id": answer_id, "valid_until": valid_until})
    return trace


def test_oracle_and_pipeline_agree_on_5000_query_trace():
    trace = build_trace(N_QUERIES, N_DISTINCT_ANSWERS, seed=7)

    oracle = ReferenceCache(threshold=THRESHOLD)
    pipeline_index = LinearScanIndex()
    valid_until_by_entry = {}

    disagreements = []
    for i, row in enumerate(trace):
        now = row["t"]
        embedding = make_embedding(row["answer_id"])

        oracle_decision, _ = oracle.decide(list(embedding), now)

        gate = TrueValidityGate(valid_until_by_entry)
        pipeline_decision, _ = decide(
            embedding, pipeline_index, threshold=THRESHOLD, gate=gate, now=now
        )

        if oracle_decision != pipeline_decision:
            disagreements.append((i, oracle_decision, pipeline_decision))

        if oracle_decision != Decision.HIT:
            # Keyed by answer_id, not by query index: a refresh must replace the stale
            # entry rather than add a second one under the same embedding, on both
            # sides, or the two structures diverge on which entry a later query finds.
            entry_id = row["answer_id"]
            meta = EntryMeta(
                entry_id=entry_id,
                cluster_id=row["answer_id"] % 10,
                answer_id=row["answer_id"],
                create_on=now,
                last_access=now,
                valid_until=row["valid_until"],
                freq=0.0,
                regen_cost=0.001,
                size_bytes=100,
            )
            oracle.insert(list(embedding), meta)
            pipeline_index.insert(embedding, meta)
            valid_until_by_entry[entry_id] = row["valid_until"]

    assert disagreements == [], f"found {len(disagreements)} disagreements: {disagreements[:5]}"
