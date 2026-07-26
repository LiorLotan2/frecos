"""Fair test of FreCoS eviction's cost-awareness: gate off, so eviction sees the full
range of entries (not just gate-protected fresh ones), heterogeneous per-cluster
regeneration costs (already how workloads.w1_synthetic.generator draws regen_cost -- no
generator change needed), scored on cost_saved_usd rather than stale-hit-rate.

Every prior ablation in this project ran with the gate on, which pre-filters out stale
entries before eviction ever sees them -- eviction then only ever chooses among entries
the gate has already certified fresh, so FreCoS's regen_cost and decay terms had nothing
to differentiate on beyond what the gate had already decided. This is the first
experiment in this project where FreCoS's eviction value function is tested on the
metric it was designed to move (cost_saved_usd, not stale_hit_rate) without a gate
already doing most of the work in front of it.

Design: W1 eval split, gate disabled (NullGate), three eviction policies (FreCoS, LFU,
LRU) x 10 seeds each, same trace scale and cache size as the main ablation
(n_queries=12000, cache_size_entries=1650).
"""
import os

from gptcache_ext.config import Config
from gptcache_ext.eviction.baselines import LFUEviction, LRUEviction
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.pipeline import NullGate
from gptcache_ext.staleness.fitter import fit_staleness_table
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.embedding_pipeline import SEMANTIC_THRESHOLD, get_shared_embedder, prepare_trace
from benchmarks.capture_env import write_env_json
from benchmarks.harness import run_harness, write_csv_row
from benchmarks.semantic_index import SemanticIndex

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 12000
CACHE_SIZE_ENTRIES = 1650
TTL_CONFIDENCE = 0.9
SEEDS = list(range(10))

RESULTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "results", "cost_aware_eviction"
)
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")

ROWS = [
    ("row1_frecos", "FRECOS"),
    ("row2_lfu", "LFU"),
    ("row3_lru", "LRU"),
]


def build_eviction(policy_name, staleness_table):
    if policy_name == "FRECOS":
        return FreCoSEviction(staleness_table)
    if policy_name == "LFU":
        return LFUEviction()
    if policy_name == "LRU":
        return LRUEviction()
    raise ValueError(f"unknown eviction policy {policy_name!r}")


def run_one(row_name, policy_name, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
    )
    cluster_ari = prepare_trace(trace, n_clusters=N_CLUSTERS, seed=seed)

    # FreCoS still needs a staleness table for its decay term even with the gate off;
    # fitting it here (never consulted by NullGate) keeps the policy's lambda_c lookup
    # meaningful rather than passing it a table built from a different trace.
    staleness_table = fit_staleness_table(trace, mode="learned", confidence=TTL_CONFIDENCE)
    eviction_policy = build_eviction(policy_name, staleness_table)

    config = Config(
        gate_enabled=False,
        eviction_policy=policy_name,
        cache_size_entries=CACHE_SIZE_ENTRIES,
        cluster_count_k=N_CLUSTERS,
        ttl_confidence=TTL_CONFIDENCE,
        lambda_source="none",
        seed=seed,
    )
    index = SemanticIndex(CACHE_SIZE_ENTRIES, eviction_policy, get_shared_embedder())
    run_id = f"cost-aware-w1-{row_name}-seed{seed}"
    return run_harness(
        trace, config, seed=seed, gate=NullGate(), eviction_policy=eviction_policy,
        staleness_table=staleness_table, workload="w1", run_id=run_id,
        index=index, threshold=SEMANTIC_THRESHOLD, cluster_ari=cluster_ari,
    )


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_env_json(RESULTS_DIR)
    if os.path.exists(RESULTS_CSV):
        os.remove(RESULTS_CSV)

    for row_name, policy_name in ROWS:
        for seed in SEEDS:
            row = run_one(row_name, policy_name, seed)
            write_csv_row(row, RESULTS_CSV)
            print(
                f"{row_name} seed={seed} n_hits={row['n_hits']} "
                f"cost_saved_usd={row['cost_saved_usd']:.4f} "
                f"stale_hit_rate={row['stale_hit_rate']:.4f}"
            )


if __name__ == "__main__":
    main()
