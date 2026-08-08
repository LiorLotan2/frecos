"""Brute-force cosine-similarity index: same Index protocol and same storage/eviction
contract as benchmarks.harness.ExactMatchIndex, but search() ranks by cosine similarity
against a NumPy matrix of cached-entry embeddings instead of doing exact-text lookup.

The scale here (thousands of cached entries at most) is far below where a vector-DB
dependency would earn its keep: a dense matmul against the cache's own embedding matrix is
fast enough that this stays a NumPy-only module.

Inherits bump_freq from ExactMatchIndex, which does not advance last_access, so LRUEviction
behaves as insertion-order eviction here too. See benchmarks/harness.py's module docstring.
"""
import numpy as np

from benchmarks.harness import ExactMatchIndex, _Candidate


class SemanticIndex(ExactMatchIndex):
    """Subclasses ExactMatchIndex for storage/eviction bookkeeping; only search() and
    the embedding-cache lifecycle (insert/evict) differ."""

    def __init__(self, budget: int, eviction_policy, embedder):
        super().__init__(budget, eviction_policy)
        self.embedder = embedder
        self._embeddings = {}

    def _embed(self, text: str) -> np.ndarray:
        if text not in self._embeddings:
            self._embeddings[text] = self.embedder.embed(text)
        return self._embeddings[text]

    def search(self, query: str):
        if not self._by_text:
            return None
        query_vec = self._embed(query)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return None

        texts = list(self._by_text.keys())
        matrix = np.stack([self._embeddings[t] for t in texts])
        norms = np.linalg.norm(matrix, axis=1)
        norms = np.where(norms == 0, 1e-12, norms)
        sims = (matrix @ query_vec) / (norms * query_norm)

        best_idx = int(np.argmax(sims))
        return _Candidate(rank=float(sims[best_idx]), meta=self._by_text[texts[best_idx]])

    def insert(self, text: str, meta_kwargs: dict, now: float):
        meta = super().insert(text, meta_kwargs, now)
        self._embed(text)
        return meta

    def _evict_if_over_budget(self, now: float, incoming: int) -> None:
        evicted_texts = set(self._by_text.keys())
        super()._evict_if_over_budget(now, incoming)
        evicted_texts -= set(self._by_text.keys())
        for text in evicted_texts:
            self._embeddings.pop(text, None)
