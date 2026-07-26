"""FreCoS eviction policy: value = log(2+freq) * log(1+kappa*regen_cost) * exp(-lambda*age).

Selectable the same way stock policies are (policy="FRECOS") via register() at the bottom,
which monkeypatches GPTCache's own EvictionBase.get() factory rather than registering a real
subclass through any extension hook, because GPTCache's factory has none: eviction/manager.py's
EvictionBase.get() is a hardcoded if/elif chain on the `name` argument (memory/redis/
no_op_eviction), with no lookup table or plugin point a caller could add to. See
tests/test_gptcache_integration.py for an end-to-end check against a real SSDataManager driven
through this factory. The scoring logic itself is plain Python and is what tests/test_frecos.py
exercises directly.

The freq term uses log(2+freq), not the log(1+freq) in the original design note: at freq=0,
log(1+0) is exactly 0 and zeroes the whole product regardless of cost, age, or size, so a
brand-new entry would always be the eviction victim. log(2+freq) keeps the same shape (still
concave, still increasing) while giving a fresh entry a strictly positive score.

No /size_bytes term: an earlier version divided by size_bytes to reward evicting large
entries first, but eviction here runs under an entry-count budget (evict one entry when the
count exceeds cache_size_entries), not a byte budget. Under a count budget, evicting a
10-byte entry and a 10,000-byte entry both free exactly one slot, so size-normalizing the
value function has no budget-economics meaning - it can only reshuffle which same-count-cost
entry gets evicted, not reward freeing more bytes, because bytes freed is never what the
budget check measures. This was verified empirically, not just derived on paper: an ablation
that dropped the /size_bytes term at the smallest cache-size point in this project's sweep
(where eviction pressure is highest) found FreCoS with and without the term statistically
indistinguishable on every metric (see results/ablation/size_term_isolation/summary.md). A
size term would only be meaningful if eviction were budgeted in bytes, which this project's
harness does not implement.
"""
import math
from typing import Optional, Sequence

from gptcache_ext.contracts import EntryMeta, StalenessTable

DEFAULT_KAPPA = 1000.0


class FreCoSEviction:
    """Implements the EvictionPolicy protocol from contracts.py.

    :param staleness_table: per-cluster lambda lookup, contracts.StalenessTable.
    :param kappa: scales regen_cost (USD, typically small) before log-compressing it.
    """

    def __init__(
        self,
        staleness_table: StalenessTable,
        kappa: float = DEFAULT_KAPPA,
    ):
        self.staleness_table = staleness_table
        self.kappa = kappa

    def value(self, meta: EntryMeta, now: float) -> float:
        age = now - meta.create_on
        lambda_c = self.staleness_table.get(meta.cluster_id).lambda_
        return (
            math.log(2.0 + meta.freq)
            * math.log1p(self.kappa * meta.regen_cost)
            * math.exp(-lambda_c * age)
        )

    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        best = min(metas, key=lambda m: (self.value(m, now), m.create_on, m.entry_id))
        return best.entry_id


def register():
    """Registers FreCoSEviction with GPTCache's own EvictionBase.get() factory, so it can
    be selected by name like any built-in policy. This is the hook the design doc points
    at (eviction/manager.py's if/elif chain) - hooked into from here rather than editing
    the vendored file, by wrapping GPTCache's EvictionBase interface (put/get/policy) and
    reading metadata back through gptcache_ext.metadata.get_meta since eviction natively
    only sees bare entry ids (data_manager.py's eviction_base.put(ids) / .get(id)).
    """
    from gptcache.manager.eviction.base import EvictionBase as GPTCacheEvictionBase
    from gptcache.manager.eviction import manager as gptcache_eviction_manager

    from gptcache_ext.metadata import MetadataStore, get_meta

    class _FreCoSEvictionBase(GPTCacheEvictionBase):
        """Adapter: GPTCache's put(ids)/get(id) interface backed by FreCoSEviction's
        value function, with metadata pulled from a MetadataStore keyed by entry_id."""

        def __init__(
            self,
            maxsize: int = 1000,
            clean_size: int = 0,
            on_evict=None,
            metadata_store: Optional[MetadataStore] = None,
            staleness_table: Optional[StalenessTable] = None,
            kappa: float = DEFAULT_KAPPA,
            **kwargs,
        ):
            self._maxsize = maxsize
            self._clean_size = clean_size or int(maxsize * 0.2)
            self._on_evict = on_evict
            self._metadata_store = metadata_store
            self._entry_ids: list = []
            self._policy = FreCoSEviction(staleness_table, kappa=kappa)

        def put(self, objs):
            self._entry_ids.extend(objs)
            overflow = len(self._entry_ids) - self._maxsize
            if overflow > 0:
                self._evict(min(overflow, self._clean_size) or overflow)

        def get(self, obj):
            return obj if obj in self._entry_ids else None

        def _evict(self, n):
            import time

            now = time.time()
            evicted = []
            for _ in range(n):
                metas = [
                    get_meta(self._metadata_store, entry_id)
                    for entry_id in self._entry_ids
                ]
                metas = [m for m in metas if m is not None]
                if not metas:
                    break
                victim_id = self._policy.select_victim(metas, now)
                self._entry_ids.remove(victim_id)
                evicted.append(victim_id)
            if evicted and self._on_evict:
                self._on_evict(evicted)

        @property
        def policy(self) -> str:
            return "FRECOS"

    original_get = gptcache_eviction_manager.EvictionBase.get

    def patched_get(name: str, policy: str = "LRU", **kwargs):
        if policy.upper() == "FRECOS":
            return _FreCoSEvictionBase(**kwargs)
        return original_get(name, policy=policy, **kwargs)

    gptcache_eviction_manager.EvictionBase.get = staticmethod(patched_get)
