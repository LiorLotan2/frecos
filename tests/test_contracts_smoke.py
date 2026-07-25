"""Smoke test for the scaffold: contracts import and construct.

Not the invariant suite or the oracle (those belong to A2). This just proves the
harness runs cleanly on a fresh clone before any other agent's code exists.
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
