"""A naive, obviously-correct semantic cache used only to check the real pipeline against.

No indexing structure, no eviction policy, no gate abstraction. Just a dict of entries, a
dict of their true expiry times, and a linear scan over every entry on every query. If you
can read this file top to bottom and believe it is correct, that is the entire point of it.

Unlike gptcache_ext/pipeline.py, this oracle checks staleness against the *true*
valid_until recorded on the entry, not against a learned TTL. That is deliberate: this is
ground truth, not another implementation of the gate. tests/test_stock_parity.py and the
pipeline/oracle agreement test construct traces where a TTL gate derived from the true
half-life reduces to exactly this check, so the two are comparable there.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from gptcache_ext.contracts import Decision, EntryMeta


@dataclass
class Entry:
    embedding: List[float]
    meta: EntryMeta


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ReferenceCache:
    """entries: entry_id -> Entry. valid_until: entry_id -> ground-truth expiry time,
    kept as an explicit separate table rather than reading it off Entry.meta, so the
    "what is the answer key" question has one obvious place to look."""

    def __init__(self, threshold: float):
        self.threshold = threshold
        self.entries: Dict[int, Entry] = {}
        self.valid_until: Dict[int, float] = {}

    def insert(self, embedding: List[float], meta: EntryMeta) -> None:
        self.entries[meta.entry_id] = Entry(embedding=embedding, meta=meta)
        self.valid_until[meta.entry_id] = meta.valid_until

    def _nearest(self, embedding: List[float]) -> Tuple[Optional[int], float]:
        best_id = None
        best_score = float("-inf")
        for entry_id, entry in self.entries.items():
            score = cosine_similarity(embedding, entry.embedding)
            if score > best_score:
                best_score = score
                best_id = entry_id
        return best_id, best_score

    def decide(
        self, embedding: List[float], now: float
    ) -> Tuple[Decision, Optional[EntryMeta]]:
        entry_id, score = self._nearest(embedding)
        if entry_id is None:
            return Decision.MISS_ABSENT, None
        if score < self.threshold:
            return Decision.MISS_THRESHOLD, None
        meta = self.entries[entry_id].meta
        if now > self.valid_until[entry_id]:
            return Decision.MISS_STALE, meta
        return Decision.HIT, meta
