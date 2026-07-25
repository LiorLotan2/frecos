"""Isolates the eviction value function's /size_bytes term under tight cache pressure.

The main ablation (ablation.py) runs FreCoS with and without the size term at
cache_size_entries=1650, where the size term turned out indistinguishable from the full
stack: with the gate already filtering out anything stale, there was little eviction
pressure left for size to differentiate on. This script reruns the same two rows, gate on,
FreCoS with and without size, at the smallest cache-size point already used in the
cache-size sweep (330 entries, 5% of the working set), where eviction happens far more
often and the size term has more candidates to actually choose between.
"""
import os

from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.harness import run_harness, write_csv_row

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 12000
CACHE_SIZE_ENTRIES = 330
TTL_CONFIDENCE = 0.9
SEEDS = list(range(10))

RESULTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "results", "ablation", "size_term_isolation"
)
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")

ROWS = [
    ("row5_gate_frecos_smallcache", False),
    ("row6_gate_frecos_nosize_smallcache", True),
]


def run_one(row_name, no_size, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
    )
    staleness_table = fit_staleness_table(trace, mode="learned", confidence=TTL_CONFIDENCE)
    gate = TTLGate(staleness_table)
    eviction_policy = FreCoSEviction(staleness_table, no_size=no_size)
    config = Config(
        gate_enabled=True,
        eviction_policy="FRECOS_NOSIZE" if no_size else "FRECOS",
        cache_size_entries=CACHE_SIZE_ENTRIES,
        cluster_count_k=N_CLUSTERS,
        ttl_confidence=TTL_CONFIDENCE,
        lambda_source="learned",
        seed=seed,
    )
    run_id = f"ablation-w1-{row_name}-seed{seed}"
    return run_harness(
        trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
        staleness_table=staleness_table, workload="w1", run_id=run_id,
    )


def main():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    if os.path.exists(RESULTS_CSV):
        os.remove(RESULTS_CSV)

    for row_name, no_size in ROWS:
        for seed in SEEDS:
            row = run_one(row_name, no_size, seed)
            write_csv_row(row, RESULTS_CSV)
            print(
                f"{row_name} seed={seed} n_hits={row['n_hits']} "
                f"stale_hit_rate={row['stale_hit_rate']:.4f}"
            )


if __name__ == "__main__":
    main()
