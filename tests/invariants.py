"""Callable invariant suite. Each check is a plain function that raises AssertionError
on violation, so both pytest and (later) the benchmark harness can call them directly
without going through pytest's collection machinery.
"""
import os
from typing import Callable, List, Sequence

from gptcache_ext.contracts import ClusterStaleness, Decision, EntryMeta, EvictionPolicy

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPTCACHE_EXT_ROOT = os.path.join(_REPO_ROOT, "gptcache_ext")


def check_budget_respected(entry_count: int, budget: int) -> None:
    assert entry_count <= budget, f"entry count {entry_count} exceeds budget {budget}"


def check_select_victim_is_argmin(
    policy: EvictionPolicy, metas: Sequence[EntryMeta], now: float
) -> None:
    if not metas:
        return
    victim = policy.select_victim(metas, now)
    values = {meta.entry_id: policy.value(meta, now) for meta in metas}
    expected_min = min(values.values())
    assert values[victim] == expected_min, (
        f"select_victim returned entry {victim} with value {values[victim]}, "
        f"but the minimum value present is {expected_min}"
    )


def check_no_stale_serve(
    meta: EntryMeta, now: float, staleness_table: "StalenessTableLike", served: bool
) -> None:
    """served entries must satisfy now - create_on <= ttl_seconds for their cluster."""
    if not served:
        return
    ttl_seconds = staleness_table.get(meta.cluster_id).ttl_seconds
    age = now - meta.create_on
    assert age <= ttl_seconds, (
        f"entry {meta.entry_id} served at age {age}s, exceeding "
        f"ttl_seconds {ttl_seconds}s for cluster {meta.cluster_id}"
    )


def check_age_from_create_on_not_last_access(gate) -> None:
    """Regression case: a hot-but-old entry (high freq, recent last_access, old
    create_on) must be classified stale. If a gate reads last_access for age instead
    of create_on, this entry would wrongly look fresh."""
    now = 1_000_000.0
    hot_but_old = EntryMeta(
        entry_id=1,
        cluster_id=0,
        answer_id=1,
        create_on=now - 1_000_000.0,
        last_access=now - 1.0,
        valid_until=float("inf"),
        freq=1000.0,
        regen_cost=0.01,
        size_bytes=100,
    )
    assert gate.is_stale(hot_but_old, now), (
        "entry with old create_on but recent last_access and high freq was not "
        "classified stale; age must be computed from create_on, never last_access"
    )


def check_no_valid_until_leak() -> None:
    """valid_until is harness-only ground truth. It must appear nowhere in gptcache_ext/
    except metadata.py and contracts.py (contracts.py defines the field itself)."""
    allowed_files = {"metadata.py", "contracts.py"}
    for dirpath, _, filenames in os.walk(GPTCACHE_EXT_ROOT):
        for filename in filenames:
            if not filename.endswith(".py") or filename in allowed_files:
                continue
            path = os.path.join(dirpath, filename)
            with open(path, encoding="utf-8") as f:
                contents = f.read()
            assert "valid_until" not in contents, (
                f"{path} references valid_until, but only metadata.py may read/write "
                f"the ground-truth validity field"
            )


def check_determinism(
    decide_fn: Callable[[int], List[Decision]], seed: int
) -> None:
    """Same seed must produce an identical decision sequence on repeated calls."""
    first = decide_fn(seed)
    second = decide_fn(seed)
    assert first == second, (
        f"seed {seed} produced different decision sequences on repeated runs: "
        f"{first} != {second}"
    )


class StalenessTableLike:
    """Structural placeholder purely for the type hint above; the real StalenessTable
    protocol lives in contracts.py and is what any caller actually passes."""

    def get(self, cluster_id: int) -> ClusterStaleness:
        raise NotImplementedError
