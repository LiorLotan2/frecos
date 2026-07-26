"""Every knob later sweeps and ablations touch, in one place, so a benchmark run is
fully described by one Config instance plus a seed."""
from dataclasses import dataclass


@dataclass
class Config:
    gate_enabled: bool = False
    eviction_policy: str = "LRU"
    cache_size_entries: int = 1000
    cluster_count_k: int = 10
    ttl_confidence: float = 0.95
    lambda_source: str = "none"  # one of: none, global, learned, oracle
    seed: int = 0
