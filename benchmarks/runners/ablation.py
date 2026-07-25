"""A9 ablation experiment: isolate the contribution of the gate and of FreCoS eviction's
value function, plus a size-normalization variant.

Design (implementation-plan.md sec 4/A9, design-v2.md sec 3.2/5.2): W1 eval split, six
rows crossed with 10 seeds each.

| Row | Gate | Eviction                     | Isolates                          |
|-----|------|-------------------------------|------------------------------------|
| 1   | off  | LRU                          | stock GPTCache                     |
| 2   | off  | LFU                          | the real floor                     |
| 3   | off  | Biton & Friedman substitute  | primary comparator                 |
| 4   | on   | LFU                          | the gate alone                     |
| 5   | on   | FreCoS                       | full stack                         |
| 6   | on   | FreCoS --no-size             | size normalization ablation        |

Row 2 (LFU), not row 1 (LRU), is the comparison of record throughout: Biton & Friedman's
own finding is that LRU is weak on semantic workloads, so an improvement over LRU alone
isn't a result.

Same trace generation and cache size as A8 (brackets.py): n_tenants=5, n_clusters=10,
n_queries=12000, one fresh trace per seed (the pipeline is deterministic given a trace, so
replaying one trace ten times would give ten identical rows and nothing to bootstrap
over). cache_size_entries=1650, confirmed still 25% of the 6600 distinct answer_ids this
n_queries produces (see verify_cache_size below).
"""
import os

from gptcache_ext.config import Config
from gptcache_ext.eviction.baselines import (
    BitonFriedmanSubstituteEviction,
    LFUEviction,
    LRUEviction,
)
from gptcache_ext.eviction.frecos import FreCoSEviction
from gptcache_ext.pipeline import NullGate
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from workloads.w1_synthetic.generator import generate_trace

from benchmarks.harness import run_harness, write_csv_row

N_TENANTS = 5
N_CLUSTERS = 10
N_QUERIES = 12000
CACHE_SIZE_ENTRIES = 1650
TTL_CONFIDENCE = 0.9
SEEDS = list(range(10))

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "results", "ablation")
RESULTS_CSV = os.path.join(RESULTS_DIR, "results.csv")

ROWS = [
    ("row1_lru", False, "LRU"),
    ("row2_lfu", False, "LFU"),
    ("row3_bf", False, "BF_SUBSTITUTE"),
    ("row4_gate_lfu", True, "LFU"),
    ("row5_gate_frecos", True, "FRECOS"),
    ("row6_gate_frecos_nosize", True, "FRECOS_NOSIZE"),
]


def verify_cache_size(trace):
    distinct = len({row["answer_id"] for row in trace})
    fraction = CACHE_SIZE_ENTRIES / distinct
    assert 0.20 <= fraction <= 0.30, (
        f"cache size {CACHE_SIZE_ENTRIES} is {fraction:.2%} of {distinct} distinct "
        "answer_ids, outside the 20-30% band A8 used"
    )


def build_gate_and_table(gate_on, trace):
    if not gate_on:
        return NullGate(), None
    staleness_table = fit_staleness_table(trace, mode="learned", confidence=TTL_CONFIDENCE)
    return TTLGate(staleness_table), staleness_table


def build_eviction(policy_name, staleness_table):
    if policy_name == "LRU":
        return LRUEviction()
    if policy_name == "LFU":
        return LFUEviction()
    if policy_name == "BF_SUBSTITUTE":
        return BitonFriedmanSubstituteEviction()
    if policy_name == "FRECOS":
        return FreCoSEviction(staleness_table)
    if policy_name == "FRECOS_NOSIZE":
        return FreCoSEviction(staleness_table, no_size=True)
    raise ValueError(f"unknown eviction policy {policy_name!r}")


def run_one(row_name, gate_on, policy_name, seed):
    trace = generate_trace(
        n_tenants=N_TENANTS, n_clusters=N_CLUSTERS, n_queries=N_QUERIES, seed=seed
    )
    if seed == 0:
        verify_cache_size(trace)

    gate, staleness_table = build_gate_and_table(gate_on, trace)
    eviction_policy = build_eviction(policy_name, staleness_table)

    config = Config(
        gate_enabled=gate_on,
        eviction_policy=policy_name,
        cache_size_entries=CACHE_SIZE_ENTRIES,
        cluster_count_k=N_CLUSTERS,
        ttl_confidence=TTL_CONFIDENCE,
        lambda_source="learned" if gate_on else "none",
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

    for row_name, gate_on, policy_name in ROWS:
        for seed in SEEDS:
            row = run_one(row_name, gate_on, policy_name, seed)
            write_csv_row(row, RESULTS_CSV)
            print(
                f"{row_name} seed={seed} n_hits={row['n_hits']} "
                f"hit_rate={row['hit_rate']:.4f} "
                f"stale_hit_rate={row['stale_hit_rate']:.4f} "
                f"cost_saved_usd={row['cost_saved_usd']:.4f}"
            )


if __name__ == "__main__":
    main()
