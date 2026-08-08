"""Callable invariant suite. Each check is a plain function that raises AssertionError
on violation, so both pytest and (later) the benchmark harness can call them directly
without going through pytest's collection machinery.
"""
import os
from typing import Callable, List, Mapping, Optional, Sequence

from gptcache_ext.contracts import ClusterStaleness, Decision, EntryMeta, EvictionPolicy

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPTCACHE_EXT_ROOT = os.path.join(_REPO_ROOT, "gptcache_ext")

# The modules under gptcache_ext/ that may name the workload generator's ground-truth
# expiry field, keyed by path relative to gptcache_ext/'s parent, each with the reason it
# is exempt. Every other module there is on the serving path and must not read it.
VALID_UNTIL_READERS: Mapping[str, str] = {
    "gptcache_ext/contracts.py": "declares the EntryMeta field itself",
    "gptcache_ext/metadata.py": (
        "carries the field from the trace onto EntryMeta so the harness can score "
        "staleness after the fact; no cache decision reads it"
    ),
    "gptcache_ext/staleness/fitter.py": (
        "fits the staleness table on calib-split trace rows from the generator's expiry "
        "labels, offline, before any row becomes a cache entry; the fitted lambdas are "
        "therefore calibrated on ground truth a deployed cache could not observe"
    ),
}


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


def check_no_valid_until_leak(
    root: str = GPTCACHE_EXT_ROOT,
    allowed_readers: Optional[Mapping[str, str]] = None,
) -> None:
    """valid_until is the workload generator's ground-truth expiry label, not a signal a
    deployed cache can observe. Only the modules in allowed_readers (VALID_UNTIL_READERS
    by default, which names the staleness fitter and its reason) may name it; every other
    module under root -- the TTL gate, the eviction policies, the pipeline, anything else
    on the serving path -- must not.

    The check runs in both directions. An unlisted module that names the field fails, and
    a listed module that no longer names it fails too, so the allowlist cannot drift into
    describing reads that are not there. Scope is root, not the whole repo, because the
    benchmark harness reads the field deliberately: it is the answer key that scoring
    compares served answers against.
    """
    if allowed_readers is None:
        allowed_readers = VALID_UNTIL_READERS
    scope = os.path.dirname(os.path.abspath(root))
    readers_found = set()
    for dirpath, _, filenames in os.walk(root):
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, scope).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                contents = f.read()
            if "valid_until" not in contents:
                continue
            assert rel in allowed_readers, (
                f"{rel} references valid_until, the generator's ground-truth expiry "
                f"field. Serving-path code must not read it. If the read is genuinely "
                f"offline, add the file to VALID_UNTIL_READERS with the reason, so the "
                f"dependency on ground truth is stated rather than hidden."
            )
            readers_found.add(rel)
    unread = sorted(set(allowed_readers) - readers_found)
    assert not unread, (
        f"VALID_UNTIL_READERS records {unread} as reading valid_until, but no such read "
        f"is present. Drop the entry so the allowlist keeps describing the tree it "
        f"guards."
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
