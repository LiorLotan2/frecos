"""Baseline eviction policies conforming to the EvictionPolicy protocol: LRU, LFU, and a
substitute for Biton & Friedman's released policy (arXiv:2603.03301).

Biton & Friedman's released implementation is not vendored here: neither this repo nor the
pinned GPTCache tree under vendor/ carries a copy or cached artifact of it, and it was
never obtained. Rather than drop the comparator silently, this module ships
BitonFriedmanSubstituteEviction, a documented LFU-with-cost variant used in its place; its
formula and the reasoning behind it are in the class docstring below. This is a
substitution, not a reproduction of their method, and the report labels it as one.
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

    Formula: value = freq * regen_cost. Reasoning: their paper's own finding is that
    frequency-based policies are the strong baseline on semantic workloads (LRU is weak),
    and this project's one signal beyond plain frequency that a cost-aware comparator
    should plausibly use is regen_cost, which is already on EntryMeta. Multiplying
    frequency by cost means a low-frequency entry that is also cheap to regenerate is
    evicted before a low-frequency entry that is expensive to regenerate, the direction
    GDSF's cost-times-frequency score takes and the direction FreCoS's own cost term takes.
    It is a product, not a lexicographic frequency-then-cost order: a cheap enough entry
    can be evicted ahead of a rarer but expensive one. Not a reimplementation of their
    recency/frequency/locality combination.
    """

    def value(self, meta: EntryMeta, now: float) -> float:
        return meta.freq * meta.regen_cost

    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        return _select_victim_by(metas, lambda m: m.freq * m.regen_cost)
