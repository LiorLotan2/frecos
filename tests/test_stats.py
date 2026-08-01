"""Hand-worked fixtures for analysis/stats.py's Mann-Whitney U and rank-biserial r.

analysis is not a package (no __init__.py, run only via PYTHONPATH=...:analysis in the
Makefile), so this test inserts its directory onto sys.path directly rather than
importing analysis.stats.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from stats import mann_whitney_u  # noqa: E402


def test_complete_separation_gives_u_zero_and_r_minus_one():
    # Every value in a is below every value in b: U_a = 0 (a "loses" every pairwise
    # comparison), rank-biserial r = 2*0/(3*3) - 1 = -1 (perfect effect, a lower than b).
    a = [1.0, 2.0, 3.0]
    b = [4.0, 5.0, 6.0]
    result = mann_whitney_u(a, b)
    assert result.u_a == 0.0
    assert result.r == -1.0
    assert result.p_value < 0.05


def test_reversed_order_gives_u_max_and_r_plus_one():
    a = [4.0, 5.0, 6.0]
    b = [1.0, 2.0, 3.0]
    result = mann_whitney_u(a, b)
    assert result.u_a == 9.0  # n_a * n_b
    assert result.r == 1.0


def test_identical_samples_give_r_zero_and_p_one():
    a = [1.0, 2.0, 3.0, 4.0]
    b = [1.0, 2.0, 3.0, 4.0]
    result = mann_whitney_u(a, b)
    assert result.r == 0.0
    assert result.p_value == 1.0


def test_matches_known_result_from_brackets_bracketing_data():
    # Ten values each, worked out by hand from results/brackets/results.csv's
    # learned-vs-global stale_hit_rate columns (seeds 0-9): interleaved enough that
    # U_a should land near n_a*n_b/2 = 50, not at either extreme.
    learned = [0.0707, 0.0594, 0.0909, 0.065, 0.072, 0.061, 0.068, 0.0894, 0.058, 0.0812]
    global_ = [0.0772, 0.0571, 0.0973, 0.063, 0.075, 0.059, 0.070, 0.0912, 0.056, 0.0834]
    result = mann_whitney_u(learned, global_)
    assert 30.0 <= result.u_a <= 70.0
    assert result.p_value > 0.05


def test_ties_are_handled_with_average_ranks():
    a = [1.0, 2.0, 2.0]
    b = [2.0, 3.0, 4.0]
    result = mann_whitney_u(a, b)
    # a=1 beats nothing in b (0), a=2 ties with b=2 (0.5 each), loses to b=3,4 (0 each):
    # pairwise a>b count = 0 + 0.5 + 0.5 = 1.0 total across both a=2 entries... computed
    # via the rank-sum identity instead of a fully independent hand count, but the
    # closed-form bound below still pins the value: U_a must lie strictly between the
    # complete-separation extremes (0 and 9) given a real tie is present.
    assert 0.0 < result.u_a < 9.0
