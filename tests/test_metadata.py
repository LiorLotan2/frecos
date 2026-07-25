"""Unit tests for MetadataStore, the additive EntryMeta adapter over CacheStorage."""
from datetime import datetime

from gptcache_ext.metadata import MetadataStore


class FakeCacheData:
    """Stands in for gptcache.manager.scalar_data.base.CacheData: only the two fields
    MetadataStore reads (create_on, last_access) matter here."""

    def __init__(self, create_on=None, last_access=None):
        self.create_on = create_on
        self.last_access = last_access


class FakeStorage:
    """Stands in for a CacheStorage; get_data_by_id is the only method the contract
    requires MetadataStore to call."""

    def __init__(self):
        self._by_id = {}

    def put(self, entry_id, cache_data):
        self._by_id[entry_id] = cache_data

    def get_data_by_id(self, key):
        return self._by_id.get(key)


def test_get_meta_returns_none_when_storage_has_no_entry():
    store = MetadataStore(FakeStorage())
    assert store.get_meta(entry_id=1) is None


def test_get_meta_combines_storage_timestamps_with_additive_fields():
    storage = FakeStorage()
    create_on = datetime(2026, 1, 1, 0, 0, 0)
    last_access = datetime(2026, 1, 2, 0, 0, 0)
    storage.put(1, FakeCacheData(create_on=create_on, last_access=last_access))

    store = MetadataStore(storage)
    store.put(
        entry_id=1,
        cluster_id=3,
        answer_id=42,
        create_on=create_on.timestamp(),
        valid_until=float("inf"),
        regen_cost=0.002,
        size_bytes=512,
    )

    meta = store.get_meta(1)
    assert meta.entry_id == 1
    assert meta.cluster_id == 3
    assert meta.answer_id == 42
    assert meta.create_on == create_on.timestamp()
    assert meta.last_access == last_access.timestamp()
    assert meta.regen_cost == 0.002
    assert meta.size_bytes == 512


def test_get_meta_falls_back_to_recorded_create_on_when_storage_has_no_timestamps():
    # MapDataManager-backed storages never set create_on/last_access on CacheData at
    # all, unlike the SQL storage. get_meta must still return a usable create_on.
    storage = FakeStorage()
    storage.put(1, FakeCacheData(create_on=None, last_access=None))

    store = MetadataStore(storage)
    store.put(
        entry_id=1,
        cluster_id=0,
        answer_id=1,
        create_on=1000.0,
        valid_until=float("inf"),
        regen_cost=0.0,
        size_bytes=0,
    )

    meta = store.get_meta(1)
    assert meta.create_on == 1000.0
    assert meta.last_access == 1000.0


def test_bump_freq_updates_returned_meta():
    storage = FakeStorage()
    storage.put(1, FakeCacheData())
    store = MetadataStore(storage)
    store.put(
        entry_id=1,
        cluster_id=0,
        answer_id=1,
        create_on=0.0,
        valid_until=float("inf"),
        regen_cost=0.0,
        size_bytes=0,
    )

    store.bump_freq(1, freq=5.0)
    assert store.get_meta(1).freq == 5.0
