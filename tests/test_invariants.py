"""Unit tests exercising the callable invariant suite itself."""
from dataclasses import dataclass

import pytest

from gptcache_ext.contracts import ClusterStaleness, Decision, EntryMeta
from gptcache_ext.pipeline import NullGate, decide
from tests.invariants import (
    check_age_from_create_on_not_last_access,
    check_budget_respected,
    check_determinism,
    check_no_stale_serve,
    check_no_valid_until_leak,
    check_select_victim_is_argmin,
)


def make_meta(entry_id, create_on=0.0, freq=0.0, regen_cost=0.0, size_bytes=1, cluster_id=0):
    return EntryMeta(
        entry_id=entry_id,
        cluster_id=cluster_id,
        answer_id=entry_id,
        create_on=create_on,
        last_access=create_on,
        valid_until=float("inf"),
        freq=freq,
        regen_cost=regen_cost,
        size_bytes=size_bytes,
    )


def test_check_budget_respected_passes_within_budget():
    check_budget_respected(entry_count=5, budget=10)


def test_check_budget_respected_fails_over_budget():
    with pytest.raises(AssertionError):
        check_budget_respected(entry_count=11, budget=10)


class ValuePolicy:
    """value() is just entry_id, so the minimum is always the lowest-id entry."""

    def value(self, meta: EntryMeta, now: float) -> float:
        return float(meta.entry_id)

    def select_victim(self, metas, now: float) -> int:
        return min(metas, key=lambda m: m.entry_id).entry_id


def test_check_select_victim_is_argmin_passes_for_correct_policy():
    metas = [make_meta(1), make_meta(2), make_meta(3)]
    check_select_victim_is_argmin(ValuePolicy(), metas, now=0.0)


class WrongPolicy(ValuePolicy):
    def select_victim(self, metas, now: float) -> int:
        return max(metas, key=lambda m: m.entry_id).entry_id


def test_check_select_victim_is_argmin_fails_for_wrong_policy():
    metas = [make_meta(1), make_meta(2), make_meta(3)]
    with pytest.raises(AssertionError):
        check_select_victim_is_argmin(WrongPolicy(), metas, now=0.0)


class FixedTTLTable:
    def __init__(self, ttl_seconds):
        self._ttl_seconds = ttl_seconds

    def get(self, cluster_id: int) -> ClusterStaleness:
        return ClusterStaleness(
            cluster_id=cluster_id, lambda_=0.0, ttl_seconds=self._ttl_seconds, n_obs=100
        )


def test_check_no_stale_serve_passes_within_ttl():
    meta = make_meta(1, create_on=0.0)
    check_no_stale_serve(meta, now=50.0, staleness_table=FixedTTLTable(100.0), served=True)


def test_check_no_stale_serve_fails_past_ttl():
    meta = make_meta(1, create_on=0.0)
    with pytest.raises(AssertionError):
        check_no_stale_serve(meta, now=150.0, staleness_table=FixedTTLTable(100.0), served=True)


def test_check_no_stale_serve_skips_when_not_served():
    meta = make_meta(1, create_on=0.0)
    check_no_stale_serve(meta, now=150.0, staleness_table=FixedTTLTable(100.0), served=False)


class TTLGateForTest:
    def __init__(self, ttl_seconds):
        self._ttl_seconds = ttl_seconds

    def is_stale(self, meta: EntryMeta, now: float) -> bool:
        return (now - meta.create_on) > self._ttl_seconds


def test_check_age_from_create_on_not_last_access_passes_for_correct_gate():
    check_age_from_create_on_not_last_access(TTLGateForTest(ttl_seconds=100.0))


class LastAccessGate:
    """A buggy gate that reads last_access for age instead of create_on."""

    def is_stale(self, meta: EntryMeta, now: float) -> bool:
        return (now - meta.last_access) > 100.0


def test_check_age_from_create_on_not_last_access_fails_for_buggy_gate():
    with pytest.raises(AssertionError):
        check_age_from_create_on_not_last_access(LastAccessGate())


def test_check_no_valid_until_leak_passes_on_current_tree():
    check_no_valid_until_leak()


def test_check_determinism_passes_for_deterministic_function():
    def decide_fn(seed):
        return [Decision.HIT, Decision.MISS_ABSENT]

    check_determinism(decide_fn, seed=1)


def test_check_determinism_fails_for_nondeterministic_function():
    calls = {"n": 0}

    def decide_fn(seed):
        calls["n"] += 1
        return [Decision.HIT] if calls["n"] == 1 else [Decision.MISS_ABSENT]

    with pytest.raises(AssertionError):
        check_determinism(decide_fn, seed=1)


def test_check_determinism_over_seeded_pipeline_run():
    """End-to-end determinism check: same seed drives the same query stream through
    decide() and must produce the same decision sequence both times."""
    import random

    @dataclass
    class Candidate:
        rank: float
        meta: EntryMeta

    def run(seed):
        rng = random.Random(seed)
        vocab = [f"q{i}" for i in range(20)]
        entries = {}
        decisions = []
        for i in range(200):
            query = rng.choice(vocab)
            meta = entries.get(query)
            candidate = Candidate(rank=1.0, meta=meta) if meta is not None else None

            class Index:
                def search(self, q):
                    return candidate

            decision, _ = decide(query, Index(), threshold=0.5, gate=NullGate(), now=float(i))
            decisions.append(decision)
            if decision != Decision.HIT:
                entries[query] = make_meta(i, create_on=float(i))
        return decisions

    check_determinism(run, seed=123)
