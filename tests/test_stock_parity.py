"""With NullGate and LRU eviction, gptcache_ext.pipeline.decide() must make exactly the
same hit/miss decisions as stock GPTCache's own adapter path. This replays 10,000
synthetic queries through both and asserts zero divergences.

This test does not use the W1 workload generator; the stream here is a small, seeded,
local helper: a mix of repeated and novel query strings, which is enough to exercise
LRU eviction and exact-match hits/misses identically on both sides.
"""
import random
from dataclasses import dataclass
from typing import Optional

from gptcache import Cache
from gptcache.adapter.api import get as stock_get
from gptcache.adapter.api import put as stock_put
from gptcache.manager import get_data_manager
from gptcache.processor.pre import get_prompt
from gptcache.similarity_evaluation import ExactMatchEvaluation

from gptcache_ext.contracts import Decision, EntryMeta
from gptcache_ext.pipeline import NullGate, decide

N_QUERIES = 10_000
CACHE_SIZE = 200
VOCAB_SIZE = 400


def synthetic_query_stream(n, vocab_size, seed):
    rng = random.Random(seed)
    return [f"query-{rng.randrange(vocab_size)}" for _ in range(n)]


def build_stock_cache(data_path):
    # MapDataManager persists to data_path and reloads any pickle already sitting there,
    # so each test run needs a fresh, non-existent path to start from an empty cache.
    cache_obj = Cache()
    cache_obj.init(
        pre_embedding_func=get_prompt,
        data_manager=get_data_manager(max_size=CACHE_SIZE, data_path=str(data_path)),
        similarity_evaluation=ExactMatchEvaluation(),
    )
    return cache_obj


class ExactMatchLRUIndex:
    """Mirrors the same exact-match + LRU-eviction semantics stock GPTCache's
    MapDataManager gives it, but exposed as an Index for decide() to call."""

    def __init__(self, maxsize):
        import cachetools

        self._entries = cachetools.LRUCache(maxsize=maxsize)
        self._next_id = 0

    def insert(self, text, now):
        entry_id = self._next_id
        self._next_id += 1
        meta = EntryMeta(
            entry_id=entry_id,
            cluster_id=0,
            answer_id=entry_id,
            create_on=now,
            last_access=now,
            valid_until=float("inf"),
            freq=0.0,
            regen_cost=0.0,
            size_bytes=0,
        )
        self._entries[text] = meta

    def search(self, text) -> Optional["Candidate"]:
        meta = self._entries.get(text)
        if meta is None:
            return None
        return Candidate(rank=1.0, meta=meta)


@dataclass
class Candidate:
    rank: float
    meta: EntryMeta


def test_zero_divergences_over_10000_queries(tmp_path):
    stream = synthetic_query_stream(N_QUERIES, VOCAB_SIZE, seed=42)

    stock_cache = build_stock_cache(tmp_path / "data_map.txt")
    threshold = stock_cache.config.similarity_threshold
    ext_index = ExactMatchLRUIndex(CACHE_SIZE)

    divergences = []
    for i, query in enumerate(stream):
        stock_result = stock_get(query, cache_obj=stock_cache)
        stock_hit = stock_result is not None

        decision, _ = decide(query, ext_index, threshold=threshold, gate=NullGate(), now=float(i))
        ext_hit = decision == Decision.HIT

        if stock_hit != ext_hit:
            divergences.append((i, query, stock_hit, ext_hit))

        if not stock_hit:
            stock_put(query, f"answer-for-{query}", cache_obj=stock_cache)
        if not ext_hit:
            ext_index.insert(query, now=float(i))

    assert divergences == [], f"found {len(divergences)} divergences: {divergences[:5]}"
