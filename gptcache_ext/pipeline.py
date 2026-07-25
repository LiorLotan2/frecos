"""The single serve-path seam. GPTCache's own adapter.py (vendored, read-only) duplicates
its hit/miss logic between adapt() and aadapt() - the async path is a near-verbatim copy
of the sync one. decide() is the one function with any hit/miss branching; a sync and an
async integration must both call it directly rather than each re-implementing the
threshold/gate checks, or the two paths can silently drift apart.
"""
from typing import Optional, Protocol, Tuple

from gptcache_ext.contracts import Decision, EntryMeta, Gate


class Candidate(Protocol):
    """What an index lookup returns: a similarity rank and the metadata of the entry
    it points at."""

    rank: float
    meta: EntryMeta


class Index(Protocol):
    def search(self, query) -> Optional[Candidate]: ...


class NullGate:
    """Gate that never rejects a candidate. With NullGate, decide() reduces to stock
    GPTCache's threshold check, which is what test_stock_parity.py asserts."""

    def is_stale(self, meta: EntryMeta, now: float) -> bool:
        return False


def decide(
    query,
    index: Index,
    threshold: float,
    gate: Gate,
    now: float,
) -> Tuple[Decision, Optional[EntryMeta]]:
    candidate = index.search(query)
    if candidate is None:
        return Decision.MISS_ABSENT, None
    if candidate.rank < threshold:
        return Decision.MISS_THRESHOLD, None
    if gate.is_stale(candidate.meta, now):
        return Decision.MISS_STALE, candidate.meta
    return Decision.HIT, candidate.meta
