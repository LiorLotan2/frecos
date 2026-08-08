"""Misspecification bracket: does learned staleness still separate from global when the
true half-life distribution is not the exponential the fitter assumes?

Every other bracket run in this project (brackets.py, brackets_calibration_sweep.py) draws
W1's true half-life as Exponential(scale), which is exactly the survival model
fit_staleness_table fits. Learned tracking oracle almost exactly in those runs is partly a
consequence of that match: maximum-likelihood estimation of an exponential rate recovers
the truth well when the data really is exponential with that rate. This script breaks the
match on purpose. generate_trace's half_life_shape=2.0 draws from a Weibull with the same
mean as before (see draw_half_life in the generator), so the average staleness rate per
cluster is unchanged, but the shape is not. The fitter still assumes exponential and is now
wrong by construction.

Design is otherwise identical to brackets.py: same trace scale, same cache size, same three
lambda_source values, five seeds each.
oracle_lambdas still uses 1/half_life_scale, the true mean rate, since that is the best a
constant-hazard oracle can encode; the Weibull's shape parameter has no equivalent slot in
this project's staleness table.
"""
import os

import numpy as np

from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import cluster_params, generate_trace

from benchmarks.embedding_pipeline import SEMANTIC_THRESHOLD, get_shared_embedder, prepare_trace
from benchmarks.capture_env import write_env_json
from benchmarks.harness import run_harness, write_csv_row
from benchmarks.semantic_index import SemanticIndex

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 3000
CACHE_SIZE_ENTRIES = 412
TTL_CONFIDENCE = 0.9
HALF_LIFE_SHAPE = 2.0
SEEDS = list(range(5))
LAMBDA_SOURCES = ["global", "learned", "oracle"]

RESULTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "results", "brackets", "misspecified"
)
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")


def oracle_lambdas_for_seed(seed):
    rng = np.random.default_rng(seed)
    params = cluster_params(N_CLUSTERS, rng)
    return {c: 1.0 / params["half_life_scale"][c] for c in range(N_CLUSTERS)}


def run_one(lambda_source, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed,
        half_life_shape=HALF_LIFE_SHAPE,
    )
    cluster_ari = prepare_trace(
        trace, n_clusters=N_CLUSTERS, seed=seed, use_true_clusters=(lambda_source == "oracle")
    )

    fit_kwargs = {}
    if lambda_source == "oracle":
        fit_kwargs["oracle_lambdas"] = oracle_lambdas_for_seed(seed)
    staleness_table = fit_staleness_table(
        trace, mode=lambda_source, confidence=TTL_CONFIDENCE, **fit_kwargs
    )

    gate = TTLGate(staleness_table)
    eviction_policy = FreCoSEviction(staleness_table)
    config = Config(
        gate_enabled=True,
        eviction_policy="FRECOS",
        cache_size_entries=CACHE_SIZE_ENTRIES,
        cluster_count_k=N_CLUSTERS,
        ttl_confidence=TTL_CONFIDENCE,
        lambda_source=lambda_source,
        seed=seed,
    )
    index = SemanticIndex(CACHE_SIZE_ENTRIES, eviction_policy, get_shared_embedder())
    run_id = f"brackets-misspecified-w1-{lambda_source}-seed{seed}"
    return run_harness(
        trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
        staleness_table=staleness_table, workload="w1", run_id=run_id,
        index=index, threshold=SEMANTIC_THRESHOLD, cluster_ari=cluster_ari,
    )


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    write_env_json(RESULTS_DIR)
    if os.path.exists(RESULTS_CSV):
        os.remove(RESULTS_CSV)

    for lambda_source in LAMBDA_SOURCES:
        for seed in SEEDS:
            row = run_one(lambda_source, seed)
            write_csv_row(row, RESULTS_CSV)
            print(
                f"{lambda_source} seed={seed} n_hits={row['n_hits']} "
                f"stale_hit_rate={row['stale_hit_rate']:.4f} "
                f"cost_saved_usd={row['cost_saved_usd']:.4f}"
            )


if __name__ == "__main__":
    main()
