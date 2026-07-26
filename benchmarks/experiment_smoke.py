"""Fast CI check that the experiment path (trace generation, staleness fitting, gate,
FreCoS eviction, harness) runs end to end, at a scale CI can afford on every commit.
Not a substitute for `make experiments`: 2 seeds and 1000 queries instead of 10 seeds
and 12000, so the numbers it prints are not meant to match any committed results.csv.
"""
from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.harness import run_harness

N_QUERIES = 1000
SEEDS = [0, 1]


def main():
    for seed in SEEDS:
        trace = generate_trace(n_tenants=5, n_clusters=10, n_queries=N_QUERIES, seed=seed)
        staleness_table = fit_staleness_table(trace, mode="learned", confidence=0.9)
        gate = TTLGate(staleness_table)
        eviction_policy = FreCoSEviction(staleness_table)
        config = Config(
            gate_enabled=True,
            eviction_policy="FRECOS",
            cache_size_entries=200,
            cluster_count_k=10,
            ttl_confidence=0.9,
            lambda_source="learned",
            seed=seed,
        )
        row = run_harness(
            trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
            staleness_table=staleness_table, workload="w1",
            run_id=f"experiment-smoke-seed{seed}",
        )
        print(
            f"seed={seed} n_hits={row['n_hits']} hit_rate={row['hit_rate']:.4f} "
            f"stale_hit_rate={row['stale_hit_rate']:.4f}"
        )


if __name__ == "__main__":
    main()
