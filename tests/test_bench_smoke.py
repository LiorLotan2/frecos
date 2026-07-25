"""pytest-benchmark integration: times a full harness run over the fixed smoke trace,
and separately checks that the count/rate columns exactly match the committed sample
row (benchmarks/samples/smoke_row.json). Latency/resource columns are real wall-clock
measurements and are not compared for exact equality.
"""
import json
import os

from benchmarks.harness import CSV_COLUMNS
from benchmarks.smoke import run_smoke

SAMPLE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "benchmarks", "samples", "smoke_row.json"
)

EXACT_COLUMNS = [
    "run_id", "workload", "policy", "gate_enabled", "lambda_source", "cache_size_entries",
    "cluster_count_k", "ttl_confidence", "seed", "split",
    "n_queries", "n_hits", "n_misses", "n_stale_hits_served", "n_stale_hits_prevented",
    "n_false_hits", "hit_rate", "stale_hit_rate", "false_hit_rate",
    "cost_saved_usd", "cost_spent_usd",
]


def test_smoke_row_has_all_csv_columns():
    row = run_smoke()
    assert list(row.keys()) == CSV_COLUMNS


def test_smoke_row_reproduces_committed_sample_exactly_on_counts_and_rates():
    with open(SAMPLE_PATH) as f:
        sample = json.load(f)
    row = run_smoke()
    for column in EXACT_COLUMNS:
        assert row[column] == sample[column], f"{column}: {row[column]} != {sample[column]}"


def test_benchmark_harness_smoke_run(benchmark):
    result = benchmark(run_smoke)
    assert result["n_queries"] > 0
