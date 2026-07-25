"""The validity gate: implements the Gate protocol from contracts.py.

Reads only create_on and the cluster's fitted ttl_seconds. Never reads last_access
or the harness-only ground-truth expiry field.
"""
from gptcache_ext.contracts import EntryMeta, StalenessTable


class TTLGate:
    def __init__(self, staleness_table: StalenessTable):
        self.staleness_table = staleness_table

    def is_stale(self, meta: EntryMeta, now: float) -> bool:
        ttl_seconds = self.staleness_table.get(meta.cluster_id).ttl_seconds
        age = now - meta.create_on
        return age > ttl_seconds
