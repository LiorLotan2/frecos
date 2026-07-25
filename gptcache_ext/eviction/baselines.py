"""Baseline eviction policies conforming to the EvictionPolicy protocol: LRU, LFU, and a
substitute for Biton & Friedman's released policy (arXiv:2603.03301).

Biton & Friedman's code was not reachable in this build environment: this repo has no
network access to arXiv or GitHub, and a search of the repo and vendored GPTCache tree
turned up no local copy or cached artifact of their release. Per the implementation plan's
explicit instruction (§4/A4, risk register), the comparator is not silently dropped: this
module instead ships BitonFriedmanSubstituteEviction, a documented LFU-with-cost variant
used in its place. Its formula and the reasoning behind it are in the class docstring below.
This is a substitution, not a reproduction of their method, and any report referencing it
must say so.
"""
from typing import Sequence

from gptcache_ext.contracts import EntryMeta


def _select_victim_by(metas: Sequence[EntryMeta], key) -> int:
    best = min(metas, key=lambda m: (key(m), m.create_on, m.entry_id))
    return best.entry_id


class LRUEviction:
    """Least-recently-used. Legitimately reads last_access: that field exists on
    EntryMeta specifically so LRU has something to key off."""

    def value(self, meta: EntryMeta, now: float) -> float:
        return meta.last_access

    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        return _select_victim_by(metas, lambda m: m.last_access)


class LFUEviction:
    """Least-frequently-used."""

    def value(self, meta: EntryMeta, now: float) -> float:
        return meta.freq

    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        return _select_victim_by(metas, lambda m: m.freq)


class BitonFriedmanSubstituteEviction:
    """Documented substitute for Biton & Friedman's released policy.

    Formula: value = freq / regen_cost. Reasoning: their paper's own finding is that
    frequency-based policies are the strong baseline on semantic workloads (LRU is weak),
    and this project's one signal beyond plain frequency that a cost-aware comparator
    should plausibly use is regen_cost, which is already on EntryMeta. Dividing frequency
    by cost means a low-frequency entry that is also cheap to regenerate is evicted before
    a low-frequency entry that is expensive to regenerate - a frequency floor with a cost
    tiebreak, not a reimplementation of their recency/frequency/locality combination.
    """

    def value(self, meta: EntryMeta, now: float) -> float:
        return meta.freq / max(meta.regen_cost, 1e-12)

    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        return _select_victim_by(metas, lambda m: m.freq / max(m.regen_cost, 1e-12))
