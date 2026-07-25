"""Tests for the W1 synthetic workload generator."""
import difflib
import json
import math
import subprocess
import sys
from collections import defaultdict

import pytest

from workloads.w1_synthetic.generator import generate_trace

REQUIRED_FIELDS = {
    "t", "query_id", "text", "cluster_id", "answer_id", "valid_until",
    "regen_cost", "size_bytes", "paraphrase_of", "split",
}


@pytest.fixture(scope="module")
def trace():
    return generate_trace(n_tenants=5, n_clusters=10, n_queries=5000, seed=7)


def test_schema_valid_on_every_row(trace):
    for row in trace:
        assert set(row.keys()) == REQUIRED_FIELDS
        assert isinstance(row["t"], float)
        assert isinstance(row["query_id"], int)
        assert isinstance(row["text"], str) and row["text"]
        assert isinstance(row["cluster_id"], int)
        assert isinstance(row["answer_id"], int)
        assert isinstance(row["valid_until"], float)
        assert isinstance(row["regen_cost"], float) and row["regen_cost"] > 0
        assert isinstance(row["size_bytes"], int) and row["size_bytes"] > 0
        assert row["paraphrase_of"] is None or isinstance(row["paraphrase_of"], int)
        assert row["split"] in ("calib", "eval")


def test_t_monotonic_non_decreasing(trace):
    times = [row["t"] for row in trace]
    assert all(times[i] <= times[i + 1] for i in range(len(times) - 1))


def test_query_ids_unique(trace):
    ids = [row["query_id"] for row in trace]
    assert len(ids) == len(set(ids))


def test_every_repeating_answer_crosses_its_valid_until(trace):
    """The staleness gate can only be exercised if some later query for the same
    answer_id arrives after the earliest instance's valid_until. If no answer_id ever
    crosses its own boundary, MISS_STALE is untestable on this trace."""
    by_answer = defaultdict(list)
    for row in trace:
        by_answer[row["answer_id"]].append(row)

    repeating = {answer_id: rows for answer_id, rows in by_answer.items() if len(rows) > 1}
    assert repeating, "trace has no repeating answer_id at all, generator config is wrong"

    for answer_id, rows in repeating.items():
        rows_sorted = sorted(rows, key=lambda r: r["t"])
        earliest = rows_sorted[0]
        crossed = any(r["t"] > earliest["valid_until"] for r in rows_sorted[1:])
        assert crossed, f"answer_id {answer_id} never crosses its earliest valid_until"


def structural_similarity(text_a, text_b):
    """Proxy for semantic similarity. The project pins GPTCache's ONNX
    paraphrase-albert-onnx embedder for real similarity ranking, but that model isn't
    available in this test environment, so this checks structural closeness (character
    overlap ratio) as a weaker stand-in. It is not a substitute for running the real
    embedder, only a sanity floor: paraphrase pairs should be near-identical strings with
    a wrapped prefix/suffix, not unrelated text."""
    return difflib.SequenceMatcher(None, text_a, text_b).ratio()


def test_paraphrase_pairs_are_similar_but_not_identical(trace):
    by_id = {row["query_id"]: row for row in trace}
    paraphrase_rows = [row for row in trace if row["paraphrase_of"] is not None]
    assert paraphrase_rows

    for row in paraphrase_rows:
        canonical = by_id[row["paraphrase_of"]]
        assert canonical["answer_id"] == row["answer_id"]
        assert canonical["text"] != row["text"]
        similarity = structural_similarity(canonical["text"], row["text"])
        assert similarity > 0.6, (
            f"paraphrase of query {canonical['query_id']} too dissimilar "
            f"(similarity={similarity:.2f}): {row['text']!r}"
        )


def test_calib_eval_disjoint_in_time(trace):
    calib_times = [row["t"] for row in trace if row["split"] == "calib"]
    eval_times = [row["t"] for row in trace if row["split"] == "eval"]
    assert calib_times and eval_times
    assert max(calib_times) <= min(eval_times)


def test_calib_is_first_30_percent(trace):
    n_calib = sum(1 for row in trace if row["split"] == "calib")
    expected = round(len(trace) * 0.3)
    assert abs(n_calib - expected) <= 1


def test_longtail_queries_do_not_repeat_or_paraphrase(trace):
    by_answer = defaultdict(list)
    for row in trace:
        by_answer[row["answer_id"]].append(row)

    longtail_rows = [
        row for row in trace
        if row["paraphrase_of"] is None and len(by_answer[row["answer_id"]]) == 1
    ]
    assert longtail_rows
    for row in longtail_rows:
        assert row["paraphrase_of"] is None


def test_same_seed_generates_identical_rows():
    trace_a = generate_trace(n_tenants=5, n_clusters=10, n_queries=1000, seed=99)
    trace_b = generate_trace(n_tenants=5, n_clusters=10, n_queries=1000, seed=99)
    assert trace_a == trace_b


def test_cli_same_seed_byte_identical(tmp_path):
    out_a = tmp_path / "a.jsonl"
    out_b = tmp_path / "b.jsonl"
    script = str(tmp_path.parent / "generator_invoke_marker")
    cmd_base = [
        sys.executable, "-m", "workloads.w1_synthetic.generator",
        "--n-queries", "500", "--seed", "3",
    ]
    subprocess.run(cmd_base + ["--out", str(out_a)], check=True, cwd=_repo_root())
    subprocess.run(cmd_base + ["--out", str(out_b)], check=True, cwd=_repo_root())
    assert out_a.read_bytes() == out_b.read_bytes()


def _repo_root():
    import pathlib
    return pathlib.Path(__file__).resolve().parents[1]


def test_different_seeds_produce_different_traces():
    trace_a = generate_trace(n_tenants=5, n_clusters=10, n_queries=500, seed=1)
    trace_b = generate_trace(n_tenants=5, n_clusters=10, n_queries=500, seed=2)
    assert trace_a != trace_b


def test_valid_until_after_t(trace):
    for row in trace:
        assert row["valid_until"] >= row["t"] or math.isinf(row["valid_until"])
