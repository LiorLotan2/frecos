"""Unit tests exercising the callable invariant suite itself."""
import os
from dataclasses import dataclass

import pytest

from gptcache_ext.contracts import ClusterStaleness, Decision, EntryMeta
from gptcache_ext.pipeline import NullGate, decide
from tests.invariants import (
    VALID_UNTIL_READERS,
    check_age_from_create_on_not_last_access,
    check_budget_respected,
    check_determinism,
    check_no_stale_serve,
    check_no_valid_until_leak,
    check_select_victim_is_argmin,
)

FITTER = "gptcache_ext/staleness/fitter.py"


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


def test_check_no_valid_until_leak_allowlists_the_fitter_with_a_reason():
    """The fitter's read of the generator's expiry labels is recorded, not hidden."""
    assert FITTER in VALID_UNTIL_READERS
    assert VALID_UNTIL_READERS[FITTER].strip()


def test_check_no_valid_until_leak_fails_if_fitter_read_not_allowlisted():
    """Drop the fitter from the allowlist and the real tree must stop passing: the
    read is still there, so the check reports it rather than tolerating it."""
    without_fitter = {rel: why for rel, why in VALID_UNTIL_READERS.items() if rel != FITTER}
    with pytest.raises(AssertionError, match="fitter.py references valid_until"):
        check_no_valid_until_leak(allowed_readers=without_fitter)


def _simulated_tree(tmp_path, gate_source, fitter_source='d = row["valid_until"] - row["t"]\n'):
    """Builds a miniature gptcache_ext/ tree the leak check can be pointed at instead of
    the real one. Every allowlisted reader is present, since the check also fails on an
    allowlist entry with no matching read."""
    root = os.path.join(str(tmp_path), "gptcache_ext")
    os.makedirs(os.path.join(root, "staleness"))
    sources = {
        "contracts.py": "valid_until: float  # ground truth, harness-only\n",
        "metadata.py": "valid_until = extra.valid_until\n",
        os.path.join("staleness", "fitter.py"): fitter_source,
        os.path.join("staleness", "gate.py"): gate_source,
    }
    for rel, source in sources.items():
        with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
            f.write(source)
    return root


def test_check_no_valid_until_leak_honours_allowlist_on_simulated_tree(tmp_path):
    root = _simulated_tree(tmp_path, gate_source="age = now - meta.create_on\n")
    check_no_valid_until_leak(root=root)


def test_check_no_valid_until_leak_catches_non_allowlisted_serving_path_read(tmp_path):
    """A TTL gate that consults the ground-truth expiry field is a leak even though the
    fitter is allowlisted."""
    root = _simulated_tree(tmp_path, gate_source="stale = now > meta.valid_until\n")
    with pytest.raises(AssertionError, match="gate.py references valid_until"):
        check_no_valid_until_leak(root=root)


def test_check_no_valid_until_leak_fails_when_allowlisted_reader_has_no_read(tmp_path):
    """An allowlist entry must describe a read that exists, so the exemption cannot
    outlive the thing it excuses."""
    root = _simulated_tree(
        tmp_path,
        gate_source="age = now - meta.create_on\n",
        fitter_source="d = row['ttl_hint'] - row['t']\n",
    )
    with pytest.raises(AssertionError, match="no such read is present"):
        check_no_valid_until_leak(root=root)


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
