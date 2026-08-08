"""Mann-Whitney U and rank-biserial correlation, hand-rolled (scipy is not available in
this sandbox, same reason analysis/multiple_comparisons.py and
gptcache_ext/staleness/cluster_accuracy.py hand-roll their own statistics).

mann_whitney_u() below is the single implementation behind every Mann-Whitney
U/p/effect-size triple quoted in results/*/summary.md and report/report.tex, so those
numbers are regenerable from the per-seed CSVs rather than computed by hand and re-typed.

Effect size is rank-biserial correlation, r = 2*U_a/(n_a*n_b) - 1, NOT r = |z|/sqrt(n1+n2),
which is a z-based rank correlation and not rank-biserial at all. The two formulas disagree
materially -- e.g. a comparison with U_a = 0.0 (complete separation, every value in a below
every value in b) gives some magnitude below 1 under r = |z|/sqrt(n1+n2), against the
correct rank-biserial r = -1.0 (perfect, signed effect). Sign here means: positive
r indicates sample_a tends toward higher values than sample_b; the magnitude is what
Section 4's "large effect" language in the report refers to.
"""
import math
from collections import Counter, namedtuple

MannWhitneyResult = namedtuple("MannWhitneyResult", ["u_a", "p_value", "r"])


def _average_ranks(values):
    """1-indexed ranks over `values`, with tied values sharing their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mann_whitney_u(sample_a, sample_b):
    """Two-sided Mann-Whitney U test between sample_a and sample_b.

    Returns MannWhitneyResult(u_a, p_value, r):
    - u_a: U statistic for sample_a (the count of (a, b) pairs with a > b, ties counted
      as 0.5), computed via the rank-sum identity U_a = R_a - n_a*(n_a+1)/2.
    - p_value: two-sided normal-approximation p-value, with the standard correction to
      the variance term for tied values in the pooled sample.
    - r: rank-biserial correlation, 2*u_a/(n_a*n_b) - 1, in [-1, 1]. Positive means
      sample_a tends higher than sample_b.
    """
    n_a, n_b = len(sample_a), len(sample_b)
    n = n_a + n_b
    combined = list(sample_a) + list(sample_b)
    ranks = _average_ranks(combined)
    r_a = sum(ranks[:n_a])
    u_a = r_a - n_a * (n_a + 1) / 2.0

    mu_u = n_a * n_b / 2.0
    tie_counts = Counter(combined)
    tie_term = sum(t**3 - t for t in tie_counts.values())
    if n > 1:
        sigma2_u = (n_a * n_b / 12.0) * ((n + 1) - tie_term / (n * (n - 1)))
    else:
        sigma2_u = 0.0

    if sigma2_u <= 0:
        p_value = 1.0
    else:
        z = (u_a - mu_u) / math.sqrt(sigma2_u)
        p_value = min(2.0 * (1.0 - _norm_cdf(abs(z))), 1.0)

    r = (2.0 * u_a / (n_a * n_b) - 1.0) if n_a * n_b else 0.0
    return MannWhitneyResult(u_a=u_a, p_value=p_value, r=r)
