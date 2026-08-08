"""Trace replay harness. Produces one results-CSV row per run.

No LLM is ever called here. This is a pure trace replayer: on a miss, the "response" is
whatever answer_id the trace says was generated, at whatever regen_cost and size_bytes
the trace recorded. This is a validity limitation, not an oversight, and the report's
Experimental Setup must say so plainly.

Miss latency is simulated, not measured, since there is no LLM call to time. It is drawn
from a log-normal scaled by size_bytes, seeded per (seed, query_id) so replay order never
affects the result. This distribution is not fit to any real trace (that calibration is
out of scope here); a later pass can swap it out once real numbers exist.

Hit latency and extension overhead (index lookup + gate check) are measured for real with
time.perf_counter() around the actual decide() call.

The built-in ExactMatchIndex below is only the default fallback, used by the smoke
benchmark and tests/test_stock_parity.py. Every experiment runner behind the report passes
benchmarks.semantic_index.SemanticIndex (brute-force cosine at GPTCache's default 0.8
threshold) instead, so paraphrase pairs do hit there. Gate, eviction policy, and staleness
table are supplied by the caller and only need to satisfy the Protocols in
gptcache_ext.contracts.

bump_freq advances last_access as well as freq, so LRUEviction here is real
least-recently-used and not insertion order. That was not always true: an earlier
bump_freq preserved last_access, which silently turned every LRU row in this project into
FIFO. Peak RSS is sampled during the replay rather than read once at each end, so it is a
real high-water mark over the run.
"""
import hashlib
import math
import random
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import psutil

from gptcache_ext.contracts import Decision, EntryMeta
from gptcache_ext.pipeline import decide

from benchmarks.metrics import (
    ServedQuery,
    cost_saved_usd,
    cost_spent_usd,
    false_hit_rate,
    hit_rate,
    is_useful_hit,
    latency_stats,
    overhead_mean_ms,
    stale_hit_rate,
    throughput_qps,
    useful_hit_rate,
)

# tests/ has no __init__.py but works as an implicit namespace package (PEP 420) as
# long as the repo root is on sys.path, which the Makefile's PYTHONPATH guarantees.
# So the harness imports tests.invariants directly rather than duplicating the checks.
from tests.invariants import (
    check_age_from_create_on_not_last_access,
    check_budget_respected,
    check_no_stale_serve,
    check_no_valid_until_leak,
    check_select_victim_is_argmin,
)

CSV_COLUMNS = [
    "run_id", "workload", "policy", "gate_enabled", "lambda_source", "cache_size_entries",
    "cluster_count_k", "ttl_confidence", "seed", "split",
    "n_queries", "n_hits", "n_misses", "n_stale_hits_served", "n_stale_hits_prevented",
    "n_false_hits", "n_useful_hits",
    "hit_rate", "stale_hit_rate", "false_hit_rate", "useful_hit_rate",
    "cost_saved_usd", "cost_spent_usd",
    "latency_mean_ms", "latency_p50_ms", "latency_p95_ms", "latency_p99_ms",
    "throughput_qps", "overhead_mean_ms", "peak_rss_mb", "cpu_pct",
    "cluster_ari",
    "git_sha", "timestamp",
]

WARMUP_FRACTION = 0.1
INDEX_MATCH_RANK = 1.0
# Only ever used with ExactMatchIndex, whose search() returns INDEX_MATCH_RANK on a match
# and None otherwise, so any value below INDEX_MATCH_RANK behaves identically. It is not a
# semantic-similarity threshold: every runner behind the report passes
# benchmarks.embedding_pipeline.SEMANTIC_THRESHOLD (0.8) explicitly instead.
EXACT_MATCH_THRESHOLD = 0.5
# How often to sample RSS during a replay, in scored queries. Sampling happens outside the
# perf_counter region around decide(), so it never lands in the measured overhead.
RSS_SAMPLE_EVERY = 100


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def _seeded_rng(seed: int, query_id: int) -> random.Random:
    """Deterministic per-(seed, query_id) RNG, independent of replay order or of any
    other row's draw. A running global RNG would make the simulated latency for query
    N depend on how many queries came before it, breaking the "same seed, same query_id
    -> same latency" requirement."""
    digest = hashlib.sha256(f"{seed}:{query_id}".encode()).digest()
    local_seed = int.from_bytes(digest[:8], "big")
    return random.Random(local_seed)


def _simulate_miss_latency_ms(seed: int, query_id: int, size_bytes: int) -> float:
    """Placeholder distribution: log-normal, scaled by size_bytes. Not fit to any real
    trace (Azure LLM Inference Trace calibration is out of scope here)."""
    rng = _seeded_rng(seed, query_id)
    base_ms = rng.lognormvariate(mu=math.log(80.0), sigma=0.5)
    return base_ms * (1.0 + size_bytes / 2000.0)


class ExactMatchIndex:
    """Minimal Index (gptcache_ext.pipeline.Index protocol) backed by a dict keyed on
    exact query text. Owns entry storage and eviction so the harness has something
    concrete to drive decide() against."""

    def __init__(self, budget: int, eviction_policy):
        self.budget = budget
        self.eviction_policy = eviction_policy
        self._by_text: Dict[str, EntryMeta] = {}
        self._entry_id_to_text: Dict[int, str] = {}
        self._next_id = 0

    def search(self, query: str):
        meta = self._by_text.get(query)
        if meta is None:
            return None
        return _Candidate(rank=INDEX_MATCH_RANK, meta=meta)

    def contains(self, text: str) -> bool:
        return text in self._by_text

    def text_for_entry_id(self, entry_id: int) -> str:
        return self._entry_id_to_text[entry_id]

    def _current_metas(self) -> List[EntryMeta]:
        return list(self._by_text.values())

    def insert(self, text: str, meta_kwargs: dict, now: float) -> EntryMeta:
        entry_id = self._next_id
        self._next_id += 1
        meta = EntryMeta(entry_id=entry_id, **meta_kwargs)
        self._evict_if_over_budget(now, incoming=1)
        self._by_text[text] = meta
        self._entry_id_to_text[entry_id] = text
        return meta

    def refresh(self, text: str, meta_kwargs: dict, now: float) -> EntryMeta:
        """Replace a stale entry's metadata in place, keeping its entry_id and not
        counting against the budget as a new insert."""
        old_meta = self._by_text[text]
        meta = EntryMeta(entry_id=old_meta.entry_id, **meta_kwargs)
        self._by_text[text] = meta
        return meta

    def bump_freq(self, text: str, now: float) -> None:
        """Record a hit on an entry: increment freq and advance last_access to the serve
        time. Both are needed, freq for LFU and last_access for LRU. create_on is
        deliberately left alone, since staleness is a property of when the answer was
        generated (see tests/invariants.py's create_on-not-last_access check)."""
        meta = self._by_text[text]
        self._by_text[text] = EntryMeta(
            entry_id=meta.entry_id, cluster_id=meta.cluster_id, answer_id=meta.answer_id,
            create_on=meta.create_on, last_access=now,
            valid_until=meta.valid_until, freq=meta.freq + 1.0,
            regen_cost=meta.regen_cost, size_bytes=meta.size_bytes,
        )

    def _evict_if_over_budget(self, now: float, incoming: int) -> None:
        while len(self._by_text) + incoming > self.budget and self._by_text:
            metas = self._current_metas()
            victim_id = self.eviction_policy.select_victim(metas, now)
            check_select_victim_is_argmin(self.eviction_policy, metas, now)
            victim_text = self._entry_id_to_text.pop(victim_id)
            del self._by_text[victim_text]
        check_budget_respected(len(self._by_text) + incoming, self.budget)


@dataclass
class _Candidate:
    rank: float
    meta: EntryMeta


def _meta_kwargs_from_row(row: dict, freq: float = 0.0) -> dict:
    return dict(
        cluster_id=row["cluster_id"],
        answer_id=row["answer_id"],
        create_on=row["t"],
        last_access=row["t"],
        valid_until=row["valid_until"],
        freq=freq,
        regen_cost=row["regen_cost"],
        size_bytes=row["size_bytes"],
    )


def _replay(
    trace: Sequence[dict], config, seed: int, gate, eviction_policy, staleness_table,
    index=None, threshold: float = EXACT_MATCH_THRESHOLD, process=None,
):
    """Replays the eval split of trace through decide(), applies the 10% warmup cut,
    and returns (scored ServedQuery rows, peak RSS in bytes). Runs the invariant checks
    inline.

    index: an already-constructed Index (e.g. benchmarks.semantic_index.SemanticIndex);
    defaults to a fresh ExactMatchIndex when not supplied, preserving every existing
    caller's behavior unchanged.

    process: the psutil.Process whose RSS is sampled every RSS_SAMPLE_EVERY queries to
    build a real high-water mark. Sampling covers the warmup rows too, since the cache
    fills there."""
    check_no_valid_until_leak()
    # NullGate (gate_enabled=False) is a no-op by design and would fail this
    # regression check trivially, so it only applies when a real staleness gate
    # is wired in.
    if config.gate_enabled:
        check_age_from_create_on_not_last_access(gate)

    eval_rows = sorted((r for r in trace if r["split"] == "eval"), key=lambda r: r["t"])
    n_warmup = math.ceil(len(eval_rows) * WARMUP_FRACTION)
    warmup_rows, scored_source_rows = eval_rows[:n_warmup], eval_rows[n_warmup:]

    if index is None:
        index = ExactMatchIndex(config.cache_size_entries, eviction_policy)
    scored: List[ServedQuery] = []

    if process is None:
        process = psutil.Process()
    peak_rss = process.memory_info().rss
    n_seen = 0

    def handle(row: dict, record: bool) -> Optional[ServedQuery]:
        start = time.perf_counter()
        decision, meta = decide(
            row["text"], index, threshold=threshold, gate=gate, now=row["t"]
        )
        overhead_ms = (time.perf_counter() - start) * 1000.0

        if decision == Decision.HIT:
            # The matched entry's own storage key, not row["text"]: a semantic index
            # can match a paraphrase to a different cached text, so the two are not
            # interchangeable the way they are under exact-match lookup.
            matched_text = index.text_for_entry_id(meta.entry_id)
            index.bump_freq(matched_text, now=row["t"])
            latency_ms = overhead_ms
            served_answer_id = meta.answer_id
            served_valid_until = meta.valid_until
            regen_cost = row["regen_cost"]
        else:
            miss_latency_ms = _simulate_miss_latency_ms(seed, row["query_id"], row["size_bytes"])
            latency_ms = overhead_ms + miss_latency_ms
            served_answer_id = -1
            served_valid_until = float("inf")
            regen_cost = row["regen_cost"]
            if decision == Decision.MISS_STALE:
                # meta is the stale candidate the gate rejected; refresh it in place
                # under its own key, which may differ from row["text"] under a
                # semantic index.
                stale_text = index.text_for_entry_id(meta.entry_id)
                index.refresh(stale_text, _meta_kwargs_from_row(row), now=row["t"])
            elif not index.contains(row["text"]):
                index.insert(row["text"], _meta_kwargs_from_row(row), now=row["t"])

        if config.gate_enabled and decision == Decision.HIT:
            check_no_stale_serve(meta, row["t"], staleness_table, served=True)

        if not record:
            return None
        return ServedQuery(
            decision=decision,
            served_answer_id=served_answer_id,
            served_valid_until=served_valid_until,
            query_answer_id=row["answer_id"],
            serve_time=row["t"],
            regen_cost=regen_cost,
            latency_ms=latency_ms,
            overhead_ms=overhead_ms,
        )

    def sample_rss() -> None:
        nonlocal peak_rss, n_seen
        n_seen += 1
        if n_seen % RSS_SAMPLE_EVERY == 0:
            peak_rss = max(peak_rss, process.memory_info().rss)

    for row in warmup_rows:
        handle(row, record=False)
        sample_rss()
    for row in scored_source_rows:
        scored.append(handle(row, record=True))
        sample_rss()

    peak_rss = max(peak_rss, process.memory_info().rss)
    return scored, peak_rss


def run_harness(
    trace: Sequence[dict],
    config: Any,
    seed: int,
    gate: Any,
    eviction_policy: Any,
    staleness_table: Any,
    workload: str = "w1",
    run_id: Optional[str] = None,
    index: Any = None,
    threshold: float = EXACT_MATCH_THRESHOLD,
    cluster_ari: Optional[float] = None,
) -> Dict[str, Any]:
    """Replays trace through the pipeline and returns one plan-sec-2.4 row.

    trace: sequence of dict rows conforming to the plan sec 2.3 schema.
    config: a gptcache_ext.config.Config.
    gate, eviction_policy, staleness_table: objects satisfying the matching Protocols
        in gptcache_ext.contracts. This module never imports concrete implementations.
    index, threshold: optional Index override (e.g. benchmarks.semantic_index.
        SemanticIndex) and its matching similarity threshold; default to a fresh
        ExactMatchIndex at the exact-match threshold, preserving prior behavior.
    cluster_ari: adjusted Rand index between the true and learned cluster labels for
        this trace, when gptcache_ext.staleness.assign_real_clusters.assign_real_clusters
        was used upstream; None when the caller still uses the generator's oracle
        cluster_id directly (recorded as an empty CSV cell, never a placeholder value).
    """
    process = psutil.Process()
    process.cpu_percent(interval=None)  # primes the internal counter

    scored, peak_rss = _replay(
        trace, config, seed, gate, eviction_policy, staleness_table,
        index=index, threshold=threshold, process=process,
    )

    cpu_pct = process.cpu_percent(interval=None)
    peak_rss_mb = peak_rss / (1024 * 1024)

    n_hits = sum(1 for r in scored if r.decision == Decision.HIT)
    n_misses = len(scored) - n_hits
    n_stale_hits_served = sum(
        1 for r in scored if r.decision == Decision.HIT and r.serve_time > r.served_valid_until
    )
    n_stale_hits_prevented = sum(1 for r in scored if r.decision == Decision.MISS_STALE)
    n_false_hits = sum(
        1 for r in scored
        if r.decision == Decision.HIT and r.served_answer_id != r.query_answer_id
    )
    n_useful_hits = sum(1 for r in scored if is_useful_hit(r))
    latency_mean, latency_p50, latency_p95, latency_p99 = latency_stats(scored)

    return {
        "run_id": run_id or f"{workload}-{config.eviction_policy}-{seed}",
        "workload": workload,
        "policy": config.eviction_policy,
        "gate_enabled": config.gate_enabled,
        "lambda_source": config.lambda_source,
        "cache_size_entries": config.cache_size_entries,
        "cluster_count_k": config.cluster_count_k,
        "ttl_confidence": config.ttl_confidence,
        "seed": seed,
        "split": "eval",
        "n_queries": len(scored),
        "n_hits": n_hits,
        "n_misses": n_misses,
        "n_stale_hits_served": n_stale_hits_served,
        "n_stale_hits_prevented": n_stale_hits_prevented,
        "n_false_hits": n_false_hits,
        "n_useful_hits": n_useful_hits,
        "hit_rate": hit_rate(scored),
        "stale_hit_rate": stale_hit_rate(scored),
        "false_hit_rate": false_hit_rate(scored),
        "useful_hit_rate": useful_hit_rate(scored),
        "cost_saved_usd": cost_saved_usd(scored),
        "cost_spent_usd": cost_spent_usd(scored),
        "latency_mean_ms": latency_mean,
        "latency_p50_ms": latency_p50,
        "latency_p95_ms": latency_p95,
        "latency_p99_ms": latency_p99,
        "throughput_qps": throughput_qps(scored),
        "overhead_mean_ms": overhead_mean_ms(scored),
        "peak_rss_mb": peak_rss_mb,
        "cpu_pct": cpu_pct,
        "cluster_ari": cluster_ari,
        "git_sha": _git_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def write_csv_row(row: Dict[str, Any], path: str) -> None:
    import csv
    import os

    write_header = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
