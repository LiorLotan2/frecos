"""Frozen interface contracts: the single definition of an entry's shape, the decision
enum, and the gate/eviction/staleness Protocols. Every other module here and in
benchmarks/ codes against these rather than against each other's concrete classes, so a
signature change in this file is a change to every implementation and every caller at once.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, Sequence

class Decision(str, Enum):
    HIT            = "hit"
    MISS_ABSENT    = "miss_absent"      # index returned no candidate
    MISS_THRESHOLD = "miss_threshold"   # candidate below similarity threshold
    MISS_STALE     = "miss_stale"       # candidate rejected by validity gate

@dataclass(frozen=True)
class EntryMeta:
    entry_id:    int
    cluster_id:  int
    answer_id:   int    # ground-truth answer identity of the cached response
    create_on:   float  # unix seconds; generation time. AGE IS COMPUTED FROM THIS.
    last_access: float  # unix seconds; LRU baselines only. NEVER used for age.
    valid_until: float  # ground truth, harness-only. Cache logic MUST NOT read this.
    freq:        float  # decayed access count
    regen_cost:  float  # USD: output_tokens * price_per_token, recorded at write
    size_bytes:  int

@dataclass(frozen=True)
class ClusterStaleness:
    cluster_id:  int
    lambda_:     float  # validity decay rate, units 1/second
    ttl_seconds: float  # derived from lambda_ at the configured confidence
    n_obs:       int    # observations backing the fit

class StalenessTable(Protocol):
    def get(self, cluster_id: int) -> ClusterStaleness:
        """Returns the global fallback for an unseen cluster_id. Never raises."""

class Gate(Protocol):
    def is_stale(self, meta: EntryMeta, now: float) -> bool: ...

class EvictionPolicy(Protocol):
    def value(self, meta: EntryMeta, now: float) -> float: ...
    def select_victim(self, metas: Sequence[EntryMeta], now: float) -> int:
        """Returns victim entry_id. Deterministic: ties break on oldest create_on,
        then lowest entry_id."""
