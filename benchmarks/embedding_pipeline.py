"""One shared helper every experiment runner calls to move off oracle-perfect cluster
assignment and exact-match lookup: embed the trace's queries, replace cluster_id with a
real k-means assignment (keeping the true label for accuracy reporting), and build a
SemanticIndex over the same embedder for the harness to search against.

A single process-wide CachedEmbedder is reused across all seven runners so a text seen
in one experiment's trace never gets re-embedded in another's; see EMBED_CACHE_DIR.
"""
import os

from gptcache_ext.staleness.assign_real_clusters import assign_real_clusters
from gptcache_ext.staleness.embedder import CachedEmbedder

EMBED_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", ".embedding_cache")
SEMANTIC_THRESHOLD = 0.8

_shared_embedder = None


def get_shared_embedder() -> CachedEmbedder:
    global _shared_embedder
    if _shared_embedder is None:
        _shared_embedder = CachedEmbedder(EMBED_CACHE_DIR)
    return _shared_embedder


def prepare_trace(trace, n_clusters: int, seed: int, use_true_clusters: bool = False):
    """Mutates trace in place (see assign_real_clusters) and returns the adjusted Rand
    index between true and learned cluster labels, for the caller to pass through to
    run_harness as cluster_ari.

    use_true_clusters: after assigning learned cluster_id (needed for the ARI figure
    and for consistency with the learned/global arms), restore cluster_id to
    true_cluster_id. Oracle mode's lambda table is keyed by the generator's true
    cluster id (see oracle_lambdas_for_seed in each runner); under real, imperfect
    clustering a learned cluster id no longer maps 1:1 to a true cluster, so oracle's
    fit and serve path must keep using true cluster identity for that arm to still mean
    what it is meant to mean (the ceiling a perfect clusterer would achieve), while
    learned and global use the real learned assignment.
    """
    embedder = get_shared_embedder()
    ari = assign_real_clusters(trace, embedder, n_clusters=n_clusters, seed=seed)
    if use_true_clusters:
        for row in trace:
            row["cluster_id"] = row["true_cluster_id"]
    return ari
