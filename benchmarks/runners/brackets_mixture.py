"""Adversarial misspecification bracket: true half-life is a 50/50 mixture of two
exponentials (one fifth of the mean scale, 1.8 times the mean scale) rather than a single
exponential.

brackets_misspecified.py tried a Weibull half-life first, but a Weibull with shape 2 has
roughly half the coefficient of variation of the exponential it replaces, so that run made
the workload's staleness easier to predict, not harder, and every arm's stale-hit-rate
improved. This script is the adversarial case: a single exponential rate fit by maximum
likelihood is systematically biased for both the fast and the slow subpopulation within
one cluster, since no single rate is correct for either half of the mixture.

Design is otherwise identical to brackets.py and brackets_misspecified.py: same trace
scale, same cache size, same three lambda_source values, ten seeds each. oracle_lambdas
still uses 1/half_life_scale, since the mixture's overall mean equals the plain
exponential's, and that mean rate is the best a single-rate oracle table can encode; the
mixture's bimodal shape has no equivalent slot in this project's staleness table either.
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
N_QUERIES = 12000
CACHE_SIZE_ENTRIES = 1650
TTL_CONFIDENCE = 0.9
HALF_LIFE_MODE = "mixture"
SEEDS = list(range(10))
LAMBDA_SOURCES = ["global", "learned", "oracle"]

RESULTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "results", "brackets", "mixture"
)
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")


def oracle_lambdas_for_seed(seed):
    rng = np.random.default_rng(seed)
    params = cluster_params(N_CLUSTERS, rng)
    return {c: 1.0 / params["half_life_scale"][c] for c in range(N_CLUSTERS)}


def run_one(lambda_source, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed,
        half_life_mode=HALF_LIFE_MODE,
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
    run_id = f"brackets-mixture-w1-{lambda_source}-seed{seed}"
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
