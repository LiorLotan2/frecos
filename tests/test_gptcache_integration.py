"""Exercises gptcache_ext.eviction.frecos.register() against a real GPTCache
SSDataManager (not a stub), confirms the eviction path is genuinely wired through
GPTCache's own EvictionBase.get() factory, and asserts the victim it picks matches
FreCoSEviction.select_victim() computed directly on the same metadata.

Modeled on tests/test_stock_parity.py, which already builds a real gptcache.Cache
successfully; this test goes one step further into SSDataManager (rather than
MapDataManager) because MapDataManager never calls EvictionBase at all -- it manages
its own cachetools LRU internally, so it would not exercise register() or the
monkeypatched factory.
"""
import time
from typing import List, Optional

import numpy as np

from gptcache.manager import CacheBase
from gptcache.manager.data_manager import SSDataManager
from gptcache.manager.eviction import EvictionBase
from gptcache.manager.vector_data.base import VectorBase, VectorData

from gptcache_ext.contracts import EntryMeta
from gptcache_ext.eviction.frecos import FreCoSEviction, register
from gptcache_ext.metadata import MetadataStore
from gptcache_ext.staleness.fitter import fit_staleness_table

N_ENTRIES = 20
MAX_SIZE = 8
VECTOR_DIM = 4


class InMemoryVectorBase(VectorBase):
    """Minimal linear-scan VectorBase: enough for SSDataManager's insert/delete
    bookkeeping. This test never calls search(), so it need not be efficient or even
    correct at ranking -- only present, since SSDataManager.import_data() always calls
    mul_add()."""

    def __init__(self):
        self._vectors = {}

    def mul_add(self, datas: List[VectorData]):
        for d in datas:
            self._vectors[d.id] = d.data

    def search(self, data: np.ndarray, top_k: int):
        return []

    def rebuild(self, ids=None) -> bool:
        return True

    def delete(self, ids) -> bool:
        for entry_id in ids:
            self._vectors.pop(entry_id, None)
        return True


def build_trace(seed: int) -> List[dict]:
    rng = np.random.default_rng(seed)
    now = time.time()
    rows = []
    for i in range(N_ENTRIES):
        rows.append(
            {
                "cluster_id": i % 3,
                "answer_id": i,
                "t": now - rng.uniform(0, 10_000),
                "valid_until": now + rng.uniform(1_000, 100_000),
                "regen_cost": float(rng.uniform(0.0001, 0.01)),
                "size_bytes": int(rng.uniform(50, 5_000)),
                "split": "calib",
            }
        )
    return rows


def test_register_wires_frecos_into_gptcache_eviction_factory(tmp_path):
    register()

    trace = build_trace(seed=0)
    staleness_table = fit_staleness_table(trace, mode="learned", confidence=0.9)

    cache_base = CacheBase("sqlite", sql_url=f"sqlite:///{tmp_path}/gptcache_test.db")
    vector_base = InMemoryVectorBase()
    metadata_store = MetadataStore(cache_base)

    data_manager = SSDataManager(
        cache_base, vector_base, None,
        e=EvictionBase(
            name="memory",
            policy="FRECOS",
            maxsize=MAX_SIZE,
            clean_size=1,
            staleness_table=staleness_table,
            metadata_store=metadata_store,
        ),
        max_size=MAX_SIZE,
        clean_size=1,
    )
    assert data_manager.eviction_base.policy == "FRECOS"

    rng = np.random.default_rng(1)
    entry_ids: List[int] = []
    evicted_ids: List[int] = []
    original_evict = data_manager.eviction_base._evict

    def spying_evict(n):
        before = set(data_manager.eviction_base._entry_ids)
        original_evict(n)
        after = set(data_manager.eviction_base._entry_ids)
        evicted_ids.extend(before - after)

    data_manager.eviction_base._evict = spying_evict

    for row in trace:
        # SQLite auto-increment ids are sequential starting at 1; predicting the next
        # one lets metadata exist before save()'s eviction call needs it (eviction runs
        # synchronously inside save(), so metadata cannot be filled in afterward).
        predicted_id = len(entry_ids) + 1
        metadata_store.put(
            entry_id=predicted_id,
            cluster_id=row["cluster_id"],
            answer_id=row["answer_id"],
            create_on=row["t"],
            valid_until=row["valid_until"],
            regen_cost=row["regen_cost"],
            size_bytes=row["size_bytes"],
        )
        vec = rng.uniform(-1, 1, size=VECTOR_DIM)
        data_manager.save(
            f"query {row['answer_id']}", f"answer {row['answer_id']}", vec,
        )
        actual_id = data_manager.s.get_ids(deleted=False)[-1]
        assert actual_id == predicted_id, (
            "sqlite auto-increment id diverged from prediction; adjust predicted_id"
        )
        entry_ids.append(actual_id)

    assert evicted_ids, "expected at least one eviction with MAX_SIZE < N_ENTRIES"

    # Recompute independently, from the same metadata, which victim a bare
    # FreCoSEviction.select_victim() would have chosen at the moment just before the
    # first eviction -- the direct-call oracle this integration test checks against.
    policy = FreCoSEviction(staleness_table)
    live_before_first_eviction = entry_ids[:MAX_SIZE + 1]
    metas = _metas_for(metadata_store, live_before_first_eviction)
    now = max(m.create_on for m in metas) + 1.0
    expected_victim = policy.select_victim(metas, now)

    assert evicted_ids[0] == expected_victim, (
        f"GPTCache's real eviction path picked entry {evicted_ids[0]}, but "
        f"FreCoSEviction.select_victim() on the same metadata picks {expected_victim}"
    )


def _metas_for(metadata_store: MetadataStore, entry_ids: List[int]) -> List[EntryMeta]:
    metas: List[Optional[EntryMeta]] = [metadata_store.get_meta(i) for i in entry_ids]
    return [m for m in metas if m is not None]
