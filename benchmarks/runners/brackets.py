"""A8 bracketing experiment: does a learned per-cluster staleness lambda land between the
global (pooled) and oracle (ground-truth) brackets on stale-hit-rate?

Design (implementation-plan.md sec 4/A8, design-v2.md sec 5.3): W1 eval split, three
lambda_source values (global, learned, oracle) crossed with 10 seeds each, gate enabled,
FreCoS eviction, cache size fixed at one point. Everything else held constant except seed.

Ten distinct traces, one per seed, not one trace replayed ten times. The pipeline is fully
deterministic given a trace (eviction and the gate have no randomness of their own), so
replaying the same trace ten times would produce byte-identical rows for every "seed" and
there would be nothing to bootstrap over. Generating one fresh trace per seed is the only
way the 10-seed design in the plan does anything.

Cache size: n_queries=12000 with the generator's default stream fractions yields 6600
distinct answer_ids (4200 canonical + 2400 longtail; paraphrases and repeats reuse existing
answer_ids so they don't add to this count, and this count is deterministic given n_queries,
independent of seed). 1650 entries is 25% of that, inside the 20-30% range this card asks
for as a placeholder mid-sweep point ahead of A10's actual cache-size sweep.
"""
import os

import numpy as np

from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import cluster_params, generate_trace

from benchmarks.harness import run_harness, write_csv_row

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 12000
CACHE_SIZE_ENTRIES = 1650
TTL_CONFIDENCE = 0.9
SEEDS = list(range(10))
LAMBDA_SOURCES = ["global", "learned", "oracle"]

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "results", "brackets")
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")


def oracle_lambdas_for_seed(seed):
    """Reconstructs the generator's true per-cluster decay rates exactly, by repeating
    the identical rng draw generate_trace makes before doing anything else: rng =
    np.random.default_rng(seed) then cluster_params(n_clusters, rng). half_life is drawn
    as Exponential(scale=half_life_scale), whose rate parameter is 1/scale, so the true
    lambda per cluster is 1/half_life_scale.
    """
    rng = np.random.default_rng(seed)
    params = cluster_params(N_CLUSTERS, rng)
    return {c: 1.0 / params["half_life_scale"][c] for c in range(N_CLUSTERS)}


def run_one(lambda_source, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
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
    run_id = f"brackets-w1-{lambda_source}-seed{seed}"
    return run_harness(
        trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
        staleness_table=staleness_table, workload="w1", run_id=run_id,
    )


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
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
