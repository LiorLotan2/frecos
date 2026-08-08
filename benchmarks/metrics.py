"""Metrics computed by the harness over a replayed trace.

Every function here takes already-recorded per-query outcomes (decision, ground-truth
answer_id, ground-truth valid_until, serve time, regen_cost) and reduces them to a
number. None of this runs inside the cache/pipeline itself: valid_until is read here
only for scoring, never by gptcache_ext code, per the leak-check invariant.
"""
import math
from dataclasses import dataclass
from typing import List, Sequence

from gptcache_ext.contracts import Decision


@dataclass
class ServedQuery:
    """One scored row: what the harness recorded after calling decide() on a query."""

    decision: Decision
    served_answer_id: int  # answer_id on the entry that was served; -1 on a miss
    served_valid_until: float  # valid_until on the entry that was served; inf on a miss
    query_answer_id: int
    serve_time: float
    regen_cost: float  # trace's regen_cost for this query, charged on a miss
    latency_ms: float
    overhead_ms: float


def is_hit(row: ServedQuery) -> bool:
    return row.decision == Decision.HIT


def is_stale_hit(row: ServedQuery) -> bool:
    return is_hit(row) and row.serve_time > row.served_valid_until


def is_false_hit(row: ServedQuery) -> bool:
    return is_hit(row) and row.served_answer_id != row.query_answer_id


def is_useful_hit(row: ServedQuery) -> bool:
    """A hit that is neither stale nor false: the cache returned the right answer and
    it was still valid. is_stale_hit and is_false_hit are independent, overlapping
    predicates (a hit can be both), so n_useful must be counted directly with this
    predicate rather than derived as n_hits - n_stale - n_false, which double-subtracts
    the overlap and can go negative once both rates are large."""
    return is_hit(row) and not is_stale_hit(row) and not is_false_hit(row)


def useful_hit_rate(rows: Sequence[ServedQuery]) -> float:
    """Fraction of served hits that were useful (correct and fresh), i.e. per-hit,
    not per-scored-query -- see is_useful_hit's docstring for why this must be
    computed directly rather than from n_hits - n_stale - n_false."""
    n_hits = sum(1 for r in rows if is_hit(r))
    if n_hits == 0:
        return 0.0
    n_useful = sum(1 for r in rows if is_useful_hit(r))
    return n_useful / n_hits


def hit_rate(rows: Sequence[ServedQuery]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if is_hit(r)) / len(rows)


def stale_hit_rate(rows: Sequence[ServedQuery]) -> float:
    n_hits = sum(1 for r in rows if is_hit(r))
    if n_hits == 0:
        return 0.0
    n_stale = sum(1 for r in rows if is_stale_hit(r))
    return n_stale / n_hits


def false_hit_rate(rows: Sequence[ServedQuery]) -> float:
    n_hits = sum(1 for r in rows if is_hit(r))
    if n_hits == 0:
        return 0.0
    n_false = sum(1 for r in rows if is_false_hit(r))
    return n_false / n_hits


def cost_saved_usd(rows: Sequence[ServedQuery]) -> float:
    """Sum of regen_cost over useful hits only, i.e. hits that were neither stale nor
    false. A hit that served an expired answer, or an answer to a different question,
    saved no backend call the caller would have accepted, so counting it would flatter
    the metric. Excluding only stale hits would leave false hits in, which at this
    workload's false-hit-rate makes the number an upper bound rather than a measurement."""
    return sum(r.regen_cost for r in rows if is_useful_hit(r))


def cost_spent_usd(rows: Sequence[ServedQuery]) -> float:
    return sum(r.regen_cost for r in rows if not is_hit(r))


def _percentile(sorted_values: List[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return sorted_values[lo]
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (k - lo)


def latency_stats(rows: Sequence[ServedQuery]):
    latencies = sorted(r.latency_ms for r in rows)
    if not latencies:
        return 0.0, 0.0, 0.0, 0.0
    mean = sum(latencies) / len(latencies)
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)
    return mean, p50, p95, p99


def throughput_qps(rows: Sequence[ServedQuery]) -> float:
    """Queries per second implied by summed per-query latency (real hit/overhead time
    plus simulated miss time), not by the trace's arrival-time span. The trace's `t`
    values describe when queries arrive, not how long the cache took to serve them, so
    using that span would measure the workload generator's pacing, not the cache."""
    total_latency_s = sum(r.latency_ms for r in rows) / 1000.0
    if total_latency_s <= 0:
        return 0.0
    return len(rows) / total_latency_s


def overhead_mean_ms(rows: Sequence[ServedQuery]) -> float:
    if not rows:
        return 0.0
    return sum(r.overhead_ms for r in rows) / len(rows)
