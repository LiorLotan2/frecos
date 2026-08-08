"""Hand-worked fixture for benchmarks/metrics.py.

The 20 rows below and the expected numbers were worked out on paper before running any
code, specifically so the metric definitions are pinned by something other than the
implementation being tested. Derivation:

- Rows 1-8: HIT, fresh (valid_until=2000 > serve_time=1000), correct answer_id.
- Rows 9-10: HIT, stale (valid_until=500 < serve_time=1000), correct answer_id.
- Rows 11-12: HIT, fresh, wrong answer_id (false but not stale).
- Row 13: HIT, stale AND wrong answer_id (both stale and false).
- Rows 14-20: MISS (various decisions; is_hit() only checks decision == HIT so the exact
  miss subtype doesn't affect these metrics).

n_hits = 13 (rows 1-13), n_misses = 7 (rows 14-20), n = 20.
hit_rate = 13/20 = 0.65
stale hits = rows 9, 10, 13 -> 3. stale_hit_rate = 3/13
false hits = rows 11, 12, 13 -> 3. false_hit_rate = 3/13
useful hits (cost_saved counts these only, i.e. neither stale nor false) = rows 1-8 ->
8 rows. regen_cost is 0.01 on every row, so cost_saved = 8 * 0.01 = 0.08. Rows 11-12 are
fresh but answer the wrong question, so they save nothing the caller would accept.
cost_spent counts the 7 miss rows: 7 * 0.01 = 0.07.
useful hits (neither stale nor false) = rows 1-8 only -> 8. useful_hit_rate = 8/13.
Rows 9-10 are stale (excluded), 11-12 are false (excluded), 13 is both (excluded once,
not twice) -- this fixture's row 13 is exactly the overlap case that a
n_hits - n_stale - n_false reconstruction would double-subtract.
"""
from gptcache_ext.contracts import Decision

from benchmarks.metrics import (
    ServedQuery,
    cost_saved_usd,
    cost_spent_usd,
    false_hit_rate,
    hit_rate,
    stale_hit_rate,
    useful_hit_rate,
)

SERVE_TIME = 1000.0
FRESH_VALID_UNTIL = 2000.0
STALE_VALID_UNTIL = 500.0
REGEN_COST = 0.01


def _hit(answer_id, valid_until, query_answer_id):
    return ServedQuery(
        decision=Decision.HIT,
        served_answer_id=answer_id,
        served_valid_until=valid_until,
        query_answer_id=query_answer_id,
        serve_time=SERVE_TIME,
        regen_cost=REGEN_COST,
        latency_ms=1.0,
        overhead_ms=0.1,
    )


def _miss(decision, query_answer_id):
    return ServedQuery(
        decision=decision,
        served_answer_id=-1,
        served_valid_until=float("inf"),
        query_answer_id=query_answer_id,
        serve_time=SERVE_TIME,
        regen_cost=REGEN_COST,
        latency_ms=50.0,
        overhead_ms=0.1,
    )


def build_fixture():
    rows = []
    for i in range(1, 9):  # rows 1-8: fresh, correct
        rows.append(_hit(i, FRESH_VALID_UNTIL, i))
    for i in range(9, 11):  # rows 9-10: stale, correct
        rows.append(_hit(i, STALE_VALID_UNTIL, i))
    rows.append(_hit(11, FRESH_VALID_UNTIL, 99))  # false, not stale
    rows.append(_hit(12, FRESH_VALID_UNTIL, 98))  # false, not stale
    rows.append(_hit(13, STALE_VALID_UNTIL, 97))  # stale and false
    rows.append(_miss(Decision.MISS_ABSENT, 14))
    rows.append(_miss(Decision.MISS_ABSENT, 15))
    rows.append(_miss(Decision.MISS_THRESHOLD, 16))
    rows.append(_miss(Decision.MISS_THRESHOLD, 17))
    rows.append(_miss(Decision.MISS_STALE, 18))
    rows.append(_miss(Decision.MISS_STALE, 19))
    rows.append(_miss(Decision.MISS_STALE, 20))
    assert len(rows) == 20
    return rows


def test_hit_rate_matches_hand_worked_value():
    assert hit_rate(build_fixture()) == 13 / 20


def test_stale_hit_rate_matches_hand_worked_value():
    assert stale_hit_rate(build_fixture()) == 3 / 13


def test_false_hit_rate_matches_hand_worked_value():
    assert false_hit_rate(build_fixture()) == 3 / 13


def test_useful_hit_rate_matches_hand_worked_value():
    assert useful_hit_rate(build_fixture()) == 8 / 13


def test_useful_hit_rate_does_not_double_subtract_the_stale_and_false_overlap():
    # A fixture with only one hit, both stale and false: n_hits - n_stale - n_false
    # would compute 1 - 1 - 1 = -1, negative. is_useful_hit-based counting gives 0/1.
    rows = [_hit(1, STALE_VALID_UNTIL, 2)]
    assert useful_hit_rate(rows) == 0.0


def test_cost_saved_matches_hand_worked_value():
    assert abs(cost_saved_usd(build_fixture()) - 0.08) < 1e-9


def test_cost_saved_excludes_false_hits_as_well_as_stale_ones():
    # One fresh hit answering the wrong question: not stale, so a non-stale-only
    # definition would count its regen_cost. It saved nothing usable.
    rows = [_hit(1, FRESH_VALID_UNTIL, 99)]
    assert cost_saved_usd(rows) == 0.0


def test_cost_spent_matches_hand_worked_value():
    assert abs(cost_spent_usd(build_fixture()) - 0.07) < 1e-9


def test_metrics_on_empty_rows_do_not_divide_by_zero():
    assert hit_rate([]) == 0.0
    assert stale_hit_rate([]) == 0.0
    assert false_hit_rate([]) == 0.0
    assert cost_saved_usd([]) == 0.0
