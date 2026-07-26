"""Tests for gptcache_ext.eviction.frecos and gptcache_ext.eviction.baselines."""
import random

import pytest

from gptcache_ext.contracts import ClusterStaleness, EntryMeta
from gptcache_ext.eviction.baselines import (
    BitonFriedmanSubstituteEviction,
    LFUEviction,
    LRUEviction,
)
from gptcache_ext.eviction.frecos import FreCoSEviction
from tests.invariants import check_select_victim_is_argmin

NOW = 1_700_000_000.0


class FakeStalenessTable:
    """Dict-backed StalenessTable stub for testing, independent of the real fitter."""

    def __init__(self, lambdas=None, default_lambda=1e-6):
        self._lambdas = lambdas or {}
        self._default_lambda = default_lambda

    def get(self, cluster_id: int) -> ClusterStaleness:
        lambda_ = self._lambdas.get(cluster_id, self._default_lambda)
        return ClusterStaleness(
            cluster_id=cluster_id, lambda_=lambda_, ttl_seconds=1.0 / max(lambda_, 1e-12), n_obs=100
        )


def make_meta(
    entry_id=0,
    cluster_id=0,
    answer_id=0,
    create_on=NOW - 100.0,
    last_access=NOW - 1.0,
    valid_until=float("inf"),
    freq=1.0,
    regen_cost=0.001,
    size_bytes=100,
):
    return EntryMeta(
        entry_id=entry_id,
        cluster_id=cluster_id,
        answer_id=answer_id,
        create_on=create_on,
        last_access=last_access,
        valid_until=valid_until,
        freq=freq,
        regen_cost=regen_cost,
        size_bytes=size_bytes,
    )


@pytest.fixture
def policy():
    return FreCoSEviction(FakeStalenessTable())


# --- Cold-start regression -------------------------------------------------


def test_cold_start_entry_scores_above_zero(policy):
    fresh = make_meta(freq=0.0, regen_cost=0.01, size_bytes=100, create_on=NOW - 1.0)
    assert policy.value(fresh, NOW) > 0.0


# --- Monotonicity -----------------------------------------------------------


def test_monotone_increasing_in_freq(policy):
    low = make_meta(freq=1.0)
    high = make_meta(freq=10.0)
    assert policy.value(high, NOW) > policy.value(low, NOW)


def test_monotone_increasing_in_regen_cost(policy):
    low = make_meta(regen_cost=0.0001)
    high = make_meta(regen_cost=0.01)
    assert policy.value(high, NOW) > policy.value(low, NOW)


def test_monotone_decreasing_in_age(policy):
    young = make_meta(create_on=NOW - 10.0)
    old = make_meta(create_on=NOW - 100_000.0)
    assert policy.value(young, NOW) > policy.value(old, NOW)


def test_value_ignores_size_bytes(policy):
    # No /size_bytes term: eviction here runs under an entry-count budget, which gives
    # size-normalization no economics to act through (see frecos.py's module docstring).
    small = make_meta(size_bytes=10)
    large = make_meta(size_bytes=1000)
    assert policy.value(small, NOW) == policy.value(large, NOW)


# --- Deterministic tie-break -------------------------------------------------


def test_tie_break_oldest_create_on_wins():
    # Same cluster, freq, regen_cost, size, so value() ties for all three.
    a = make_meta(entry_id=5, create_on=NOW - 50.0)
    b = make_meta(entry_id=3, create_on=NOW - 200.0)
    c = make_meta(entry_id=1, create_on=NOW - 50.0)
    policy = FreCoSEviction(FakeStalenessTable())
    victim = policy.select_victim([a, b, c], NOW)
    assert victim == b.entry_id


def test_tie_break_lowest_entry_id_when_create_on_also_tied():
    a = make_meta(entry_id=5, create_on=NOW - 50.0)
    b = make_meta(entry_id=1, create_on=NOW - 50.0)
    policy = FreCoSEviction(FakeStalenessTable())
    victim = policy.select_victim([a, b], NOW)
    assert victim == b.entry_id


# --- select_victim matches brute-force argmin --------------------------------


def test_select_victim_matches_brute_force_argmin():
    rng = random.Random(12345)
    policy = FreCoSEviction(FakeStalenessTable())
    for trial in range(1000):
        n = rng.randint(1, 8)
        metas = []
        for i in range(n):
            metas.append(
                make_meta(
                    entry_id=i,
                    cluster_id=0,
                    create_on=NOW - rng.uniform(1.0, 1_000_000.0),
                    freq=rng.uniform(0.1, 100.0),
                    regen_cost=rng.uniform(0.0001, 1.0),
                    size_bytes=rng.randint(1, 10_000),
                )
            )
        victim = policy.select_victim(metas, NOW)
        values = [(policy.value(m, NOW), m.create_on, m.entry_id) for m in metas]
        expected = min(values)[2]
        assert victim == expected, f"trial {trial}: expected {expected}, got {victim}"


# --- Property tests: single-factor comparisons -------------------------------


def test_cheaper_regen_cost_evicted_first(policy):
    cheap = make_meta(entry_id=1, regen_cost=0.0001)
    expensive = make_meta(entry_id=2, regen_cost=1.0)
    victim = policy.select_victim([cheap, expensive], NOW)
    assert victim == cheap.entry_id


def test_lower_freq_evicted_first(policy):
    low = make_meta(entry_id=1, freq=1.0)
    high = make_meta(entry_id=2, freq=100.0)
    victim = policy.select_victim([low, high], NOW)
    assert victim == low.entry_id


def test_older_evicted_first(policy):
    old = make_meta(entry_id=1, create_on=NOW - 1_000_000.0)
    young = make_meta(entry_id=2, create_on=NOW - 10.0)
    victim = policy.select_victim([old, young], NOW)
    assert victim == old.entry_id


# --- last_access must never affect value() -----------------------------------


def test_value_ignores_last_access(policy):
    a = make_meta(entry_id=1, last_access=NOW - 1.0)
    b = make_meta(entry_id=1, last_access=NOW - 999_999.0)
    assert policy.value(a, NOW) == policy.value(b, NOW)


# --- Invariant suite driven by each policy -----------------------------------


def _random_metas(n, seed):
    rng = random.Random(seed)
    return [
        make_meta(
            entry_id=i,
            cluster_id=rng.randint(0, 3),
            create_on=NOW - rng.uniform(1.0, 1_000_000.0),
            freq=rng.uniform(0.1, 100.0),
            regen_cost=rng.uniform(0.0001, 1.0),
            size_bytes=rng.randint(1, 10_000),
        )
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "make_policy",
    [
        lambda: FreCoSEviction(FakeStalenessTable()),
        lambda: LRUEviction(),
        lambda: LFUEviction(),
        lambda: BitonFriedmanSubstituteEviction(),
    ],
    ids=["frecos", "lru", "lfu", "biton_friedman_substitute"],
)
def test_invariant_select_victim_is_argmin_for_each_policy(make_policy):
    policy = make_policy()
    metas = _random_metas(20, seed=7)
    check_select_victim_is_argmin(policy, metas, NOW)


# --- Baselines: legitimate use of last_access / freq -------------------------


def test_lru_evicts_least_recently_accessed():
    stale = make_meta(entry_id=1, last_access=NOW - 1_000_000.0)
    fresh = make_meta(entry_id=2, last_access=NOW - 1.0)
    victim = LRUEviction().select_victim([stale, fresh], NOW)
    assert victim == stale.entry_id


def test_lfu_evicts_least_frequently_used():
    rare = make_meta(entry_id=1, freq=1.0)
    common = make_meta(entry_id=2, freq=100.0)
    victim = LFUEviction().select_victim([rare, common], NOW)
    assert victim == rare.entry_id


def test_biton_friedman_substitute_prefers_cheap_low_freq():
    cheap_low_freq = make_meta(entry_id=1, freq=1.0, regen_cost=1.0)
    expensive_low_freq = make_meta(entry_id=2, freq=1.0, regen_cost=0.001)
    victim = BitonFriedmanSubstituteEviction().select_victim(
        [cheap_low_freq, expensive_low_freq], NOW
    )
    assert victim == cheap_low_freq.entry_id
