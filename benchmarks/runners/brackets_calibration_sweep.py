"""Bracketing follow-up: does the learned/oracle gap on stale-hit-rate open up when
calibration data is scarcer?

A per-cluster exponential MLE gets more accurate the more calibration observations it
sees, so how far learned sits from oracle depends on calibration sample size and not only
on clustering quality. Trace size is therefore an axis in its own right.

This script runs the same design as brackets.py (global/learned/oracle lambda_source x 5
seeds, gate enabled, FreCoS eviction) at a smaller trace size, chosen so calibration
observations per cluster land close to the fitter's MIN_OBSERVATIONS=30 fallback floor
(41-70 at this scale) instead of comfortably above it. n_queries=1800 rather than
brackets.py's 3000 is exactly the variable under test, which is why this runner does not
inherit that module's trace size. See results/brackets/calibration_sweep/summary.md for
the measured n_obs values and the verdict.
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
N_QUERIES = 1800
CACHE_SIZE_ENTRIES = 248
TTL_CONFIDENCE = 0.9
SEEDS = list(range(5))
LAMBDA_SOURCES = ["global", "learned", "oracle"]

RESULTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "results", "brackets", "calibration_sweep"
)
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")


def oracle_lambdas_for_seed(seed):
    """Same reconstruction as brackets.py's oracle_lambdas_for_seed: rng =
    np.random.default_rng(seed) then cluster_params(n_clusters, rng) reproduces the exact
    draw generate_trace makes before doing anything else. True lambda per cluster is
    1/half_life_scale.
    """
    rng = np.random.default_rng(seed)
    params = cluster_params(N_CLUSTERS, rng)
    return {c: 1.0 / params["half_life_scale"][c] for c in range(N_CLUSTERS)}


def run_one(lambda_source, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
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
    run_id = f"calib-sweep-w1-{lambda_source}-seed{seed}"
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
