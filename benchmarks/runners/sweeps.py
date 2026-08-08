"""Parameter sweeps: cache size, TTL confidence, cluster count K.

Design: three axes, one at a time, no full factorial. Full stack throughout (gate on,
FreCoS eviction), 5 seeds per point at the same trace scale as benchmarks/runners/
brackets.py, one fresh trace per seed for the same reason the bracketing and ablation
experiments generate fresh traces rather than replaying one -- the pipeline is
deterministic given a trace, so a repeated trace would give byte-identical "seeds" and
nothing to bootstrap over.

Fixed defaults, held constant on the two axes not being swept: cache_size_entries=495
(30% of the 1650-answer_id working set at n_queries=3000, n_clusters=10), ttl_confidence=
0.9, cluster_count_k=10. These match the bracketing experiment's calibration choices
except cache size, which the bracketing experiment fixes at 412 (25%); 495 (30%) is inside
the same plausible mid-range and is one of this sweep's own cache-size points, so the
cache-size axis includes its own default rather than defining a fourth value nobody else
uses.

Cache-size points: 82, 248, 495, 825, 1320 entries, i.e. 5%, 15%, 30%, 50%, 80% of the
1650-entry working set.

Cluster-count-K sweep varies n_clusters at trace generation time (so ground-truth cluster
structure actually changes) and passes the same k into cluster_count_k in the Config and
into the eviction/gate machinery via the staleness table, which is fit per whatever
cluster_ids appear in the trace -- no separate wiring needed, it follows from generate_trace
using n_clusters consistently. The 1650-entry working set is the same at every K value
tested here, since canonical count is max(n_clusters, round(n_queries*canonical_frac))
and every K in CLUSTER_K_POINTS is far below round(3000*0.35)=1050.
"""
import os

from gptcache_ext.config import Config
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.capture_env import write_env_json
from benchmarks.embedding_pipeline import SEMANTIC_THRESHOLD, get_shared_embedder, prepare_trace
from benchmarks.harness import run_harness, write_csv_row
from benchmarks.semantic_index import SemanticIndex

N_TENANTS = 5
N_QUERIES = 3000
SEEDS = list(range(5))

DEFAULT_CACHE_SIZE_ENTRIES = 495
DEFAULT_TTL_CONFIDENCE = 0.9
DEFAULT_N_CLUSTERS = 10

CACHE_SIZE_POINTS = [82, 248, 495, 825, 1320]
TTL_CONFIDENCE_POINTS = [0.8, 0.9, 0.95, 0.99]
CLUSTER_K_POINTS = [5, 10, 20, 50]

RESULTS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "results", "sweeps")


def run_one(cache_size_entries, ttl_confidence, n_clusters, seed, run_id_prefix):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=n_clusters, n_queries=N_QUERIES, seed=seed
    )
    cluster_ari = prepare_trace(trace, n_clusters=n_clusters, seed=seed)
    staleness_table = fit_staleness_table(trace, mode="learned", confidence=ttl_confidence)
    gate = TTLGate(staleness_table)
    eviction_policy = FreCoSEviction(staleness_table)
    config = Config(
        gate_enabled=True,
        eviction_policy="FRECOS",
        cache_size_entries=cache_size_entries,
        cluster_count_k=n_clusters,
        ttl_confidence=ttl_confidence,
        lambda_source="learned",
        seed=seed,
    )
    index = SemanticIndex(cache_size_entries, eviction_policy, get_shared_embedder())
    run_id = f"{run_id_prefix}-seed{seed}"
    return run_harness(
        trace, config, seed=seed, gate=gate, eviction_policy=eviction_policy,
        staleness_table=staleness_table, workload="w1", run_id=run_id,
        index=index, threshold=SEMANTIC_THRESHOLD, cluster_ari=cluster_ari,
    )


def run_sweep(axis_name, points, point_to_kwargs, results_dir):
    os.makedirs(results_dir, exist_ok=True)
    write_env_json(results_dir)
    results_csv = os.path.join(results_dir, "results.csv")
    if os.path.exists(results_csv):
        os.remove(results_csv)

    for point in points:
        kwargs = point_to_kwargs(point)
        for seed in SEEDS:
            run_id_prefix = f"sweep-{axis_name}-{point}"
            row = run_one(seed=seed, run_id_prefix=run_id_prefix, **kwargs)
            write_csv_row(row, results_csv)
            print(
                f"{axis_name}={point} seed={seed} n_hits={row['n_hits']} "
                f"hit_rate={row['hit_rate']:.4f} stale_hit_rate={row['stale_hit_rate']:.4f}"
            )


def main():
    run_sweep(
        "cache_size", CACHE_SIZE_POINTS,
        lambda point: dict(
            cache_size_entries=point,
            ttl_confidence=DEFAULT_TTL_CONFIDENCE,
            n_clusters=DEFAULT_N_CLUSTERS,
        ),
        os.path.join(RESULTS_ROOT, "cache_size"),
    )
    run_sweep(
        "ttl_confidence", TTL_CONFIDENCE_POINTS,
        lambda point: dict(
            cache_size_entries=DEFAULT_CACHE_SIZE_ENTRIES,
            ttl_confidence=point,
            n_clusters=DEFAULT_N_CLUSTERS,
        ),
        os.path.join(RESULTS_ROOT, "ttl_confidence"),
    )
    run_sweep(
        "cluster_k", CLUSTER_K_POINTS,
        lambda point: dict(
            cache_size_entries=DEFAULT_CACHE_SIZE_ENTRIES,
            ttl_confidence=DEFAULT_TTL_CONFIDENCE,
            n_clusters=point,
        ),
        os.path.join(RESULTS_ROOT, "cluster_k"),
    )


if __name__ == "__main__":
    main()
