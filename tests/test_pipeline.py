"""Unit tests for decide()'s four branches, independent of the oracle/parity tests."""
from dataclasses import dataclass

from gptcache_ext.contracts import Decision, EntryMeta
from gptcache_ext.pipeline import NullGate, decide

NOW = 1_000_000.0


def make_meta(entry_id=1, create_on=NOW - 10, valid_until=float("inf")):
    return EntryMeta(
        entry_id=entry_id,
        cluster_id=0,
        answer_id=entry_id,
        create_on=create_on,
        last_access=create_on,
        valid_until=valid_until,
        freq=1.0,
        regen_cost=0.001,
        size_bytes=100,
    )


@dataclass
class FakeCandidate:
    rank: float
    meta: EntryMeta


class FakeIndex:
    def __init__(self, candidate):
        self._candidate = candidate

    def search(self, query):
        return self._candidate


class AlwaysStaleGate:
    def is_stale(self, meta, now):
        return True


def test_decide_hit_when_above_threshold_and_not_stale():
    meta = make_meta()
    index = FakeIndex(FakeCandidate(rank=0.9, meta=meta))
    decision, returned_meta = decide("query", index, threshold=0.8, gate=NullGate(), now=NOW)
    assert decision == Decision.HIT
    assert returned_meta == meta


def test_decide_miss_absent_when_index_returns_no_candidate():
    index = FakeIndex(None)
    decision, meta = decide("query", index, threshold=0.8, gate=NullGate(), now=NOW)
    assert decision == Decision.MISS_ABSENT
    assert meta is None


def test_decide_miss_threshold_when_below_threshold():
    meta = make_meta()
    index = FakeIndex(FakeCandidate(rank=0.5, meta=meta))
    decision, returned_meta = decide("query", index, threshold=0.8, gate=NullGate(), now=NOW)
    assert decision == Decision.MISS_THRESHOLD
    assert returned_meta is None


def test_decide_miss_stale_when_gate_rejects():
    meta = make_meta()
    index = FakeIndex(FakeCandidate(rank=0.9, meta=meta))
    decision, returned_meta = decide(
        "query", index, threshold=0.8, gate=AlwaysStaleGate(), now=NOW
    )
    assert decision == Decision.MISS_STALE
    assert returned_meta == meta


def test_decide_rank_exactly_at_threshold_is_not_a_miss():
    meta = make_meta()
    index = FakeIndex(FakeCandidate(rank=0.8, meta=meta))
    decision, _ = decide("query", index, threshold=0.8, gate=NullGate(), now=NOW)
    assert decision == Decision.HIT


def test_null_gate_never_flags_stale():
    gate = NullGate()
    meta = make_meta(create_on=0.0, valid_until=0.0)
    assert gate.is_stale(meta, now=NOW) is False
