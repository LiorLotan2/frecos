"""Smoke test for gptcache_ext.contracts: the module imports and its types construct.

Deliberately shallow, and no substitute for the invariant suite (tests/invariants.py) or
the oracle comparison (tests/test_oracle_agreement.py). It only pins the enum values and
the immutability of the two frozen dataclasses every other module builds on.
"""
from gptcache_ext.contracts import Decision, EntryMeta, ClusterStaleness


def test_decision_enum_values():
    assert Decision.HIT == "hit"
    assert Decision.MISS_ABSENT == "miss_absent"
    assert Decision.MISS_THRESHOLD == "miss_threshold"
    assert Decision.MISS_STALE == "miss_stale"


def test_entry_meta_is_frozen():
    meta = EntryMeta(
        entry_id=1,
        cluster_id=0,
        answer_id=1,
        create_on=0.0,
        last_access=0.0,
        valid_until=float("inf"),
        freq=0.0,
        regen_cost=0.0,
        size_bytes=0,
    )
    assert meta.entry_id == 1
    try:
        meta.entry_id = 2
        assert False, "EntryMeta should be immutable"
    except AttributeError:
        pass


def test_cluster_staleness_is_frozen():
    cs = ClusterStaleness(cluster_id=0, lambda_=0.1, ttl_seconds=100.0, n_obs=50)
    assert cs.n_obs == 50
