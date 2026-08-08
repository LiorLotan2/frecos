"""Fast CI check that the experiment path (trace generation, real embedder-based
clustering, staleness fitting, gate, FreCoS eviction, real semantic index, harness)
runs end to end, at a scale CI can afford on every commit. Not a substitute for
`make experiments`: 2 seeds and 1000 queries instead of 5 seeds and 3000, so the
numbers it prints are not meant to match any committed results.csv.

Passes a real benchmarks.semantic_index.SemanticIndex and a real embedder-based
cluster assignment (benchmarks.embedding_pipeline.prepare_trace), the same objects
every results/*/results.csv-producing runner uses. Without them, run_harness()
silently defaults to ExactMatchIndex and the generator's oracle cluster_id, which
never exercises SemanticIndex or assign_real_clusters -- the exact code path that
produced every number in the report -- and lands in the ~1% exact-match hit-rate
regime instead of the real ~50-70% band, so this check would pass even if the real
path were broken.
"""
from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.embedding_pipeline import SEMANTIC_THRESHOLD, get_shared_embedder, prepare_trace
from benchmarks.harness import run_harness
from benchmarks.semantic_index import SemanticIndex

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 1000
CACHE_SIZE_ENTRIES = 200
SEEDS = [0, 1]

# The real path's hit rate sits in the 50-95% band across every experiment in this
# report; this floor only needs to rule out silently falling back to the ~1%
# exact-match regime, not pin down an exact value at this small a scale.
MIN_REALISTIC_HIT_RATE = 0.20


def main():
    for seed in SEEDS:
        trace = generate_trace(
            n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
        )
        embedder = get_shared_embedder()
        cluster_ari = prepare_trace(trace, n_clusters=N_CLUSTERS, seed=seed)
        staleness_table = fit_staleness_table(trace, mode="learned", confidence=0.9)
        gate = TTLGate(staleness_table)
        eviction_policy = FreCoSEviction(staleness_table)
        config = Config(
            gate_enabled=True,
            eviction_policy="FRECOS",
            cache_size_entries=CACHE_SIZE_ENTRIES,
            cluster_count_k=N_CLUSTERS,
            ttl_confidence=0.9,
            lambda_source="learned",
            seed=seed,
        )
        index = SemanticIndex(CACHE_SIZE_ENTRIES, eviction_policy, embedder)
        row = run_harness(
            trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
            staleness_table=staleness_table, workload="w1",
            run_id=f"experiment-smoke-seed{seed}",
            index=index, threshold=SEMANTIC_THRESHOLD, cluster_ari=cluster_ari,
        )
        print(
            f"seed={seed} n_hits={row['n_hits']} hit_rate={row['hit_rate']:.4f} "
            f"stale_hit_rate={row['stale_hit_rate']:.4f} cluster_ari={cluster_ari:.4f}"
        )
        assert row["hit_rate"] >= MIN_REALISTIC_HIT_RATE, (
            f"seed={seed} hit_rate={row['hit_rate']:.4f} is below the realistic-index "
            f"floor ({MIN_REALISTIC_HIT_RATE}) -- run_harness likely fell back to "
            f"ExactMatchIndex instead of the real SemanticIndex"
        )


if __name__ == "__main__":
    main()
