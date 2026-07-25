"""Additive metadata storage layered on top of GPTCache's CacheData.

GPTCache's scalar storage (vendor/gptcache/gptcache/manager/scalar_data/base.py) has no
columns for cluster_id, answer_id, valid_until, regen_cost, or size_bytes, and its schema
is frozen (vendored, read-only). MetadataStore is an adapter, not a subclass: it never
touches CacheData or the SQL schema, it just keeps the extra fields in a side table keyed
by entry_id and combines them with what the real storage already returns via
get_data_by_id when EntryMeta is assembled.
"""
from dataclasses import dataclass
from typing import Dict, Optional

from gptcache_ext.contracts import EntryMeta


@dataclass
class AdditiveFields:
    cluster_id: int
    answer_id: int
    create_on: float
    valid_until: float
    regen_cost: float
    size_bytes: int
    freq: float = 0.0


class MetadataStore:
    """Adapter that backs EntryMeta with a CacheStorage plus a side table of extra fields.

    :param storage: any object implementing GPTCache's CacheStorage interface
        (scalar_data/base.py), typically the same storage a DataManager already uses.
    """

    def __init__(self, storage):
        self.storage = storage
        self._fields: Dict[int, AdditiveFields] = {}

    def put(
        self,
        entry_id: int,
        cluster_id: int,
        answer_id: int,
        create_on: float,
        valid_until: float,
        regen_cost: float,
        size_bytes: int,
        freq: float = 0.0,
    ) -> None:
        self._fields[entry_id] = AdditiveFields(
            cluster_id=cluster_id,
            answer_id=answer_id,
            create_on=create_on,
            valid_until=valid_until,
            regen_cost=regen_cost,
            size_bytes=size_bytes,
            freq=freq,
        )

    def bump_freq(self, entry_id: int, freq: float) -> None:
        if entry_id in self._fields:
            self._fields[entry_id].freq = freq

    def get_meta(self, entry_id: int) -> Optional[EntryMeta]:
        cache_data = self.storage.get_data_by_id(entry_id)
        if cache_data is None:
            return None
        extra = self._fields[entry_id]

        # MapDataManager-style storages never set create_on/last_access on CacheData, so
        # fall back to the create_on recorded at write time. SQL storage sets both and
        # bumps last_access as a side effect of get_data_by_id, which is the real source
        # of truth for that field when it is available.
        create_on = (
            cache_data.create_on.timestamp() if cache_data.create_on else extra.create_on
        )
        last_access = (
            cache_data.last_access.timestamp()
            if cache_data.last_access
            else extra.create_on
        )
        return EntryMeta(
            entry_id=entry_id,
            cluster_id=extra.cluster_id,
            answer_id=extra.answer_id,
            create_on=create_on,
            last_access=last_access,
            valid_until=extra.valid_until,
            freq=extra.freq,
            regen_cost=extra.regen_cost,
            size_bytes=extra.size_bytes,
        )


def get_meta(store: MetadataStore, entry_id: int) -> Optional[EntryMeta]:
    """Free-function form of MetadataStore.get_meta, for callers that hold a store
    reference rather than the store itself."""
    return store.get_meta(entry_id)
