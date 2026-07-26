"""Holm-Bonferroni correction for the Mann-Whitney tests scattered across this
project's result summaries. scipy is not available in this sandbox (same reason every
Mann-Whitney U in this project is hand-rolled), so this is a plain implementation of
the step-down Holm procedure, not a library call.

Two primary comparisons are designated up front, per the remediation brief, and get no
correction applied to them individually (a primary comparison is tested once, on its
own account); every other test in PAIRWISE_TESTS is treated as secondary and corrected
against the rest of the secondary family.
"""
from typing import List, NamedTuple


class ComparisonResult(NamedTuple):
    label: str
    raw_p: float
    is_primary: bool
    adjusted_p: float = None


def holm_bonferroni(secondary_p_values: List[float]) -> List[float]:
    """Standard Holm step-down: sort ascending, multiply the k-th smallest by
    (n - k + 1), enforce monotonicity by taking a running max, then clip to 1.0.
    """
    n = len(secondary_p_values)
    order = sorted(range(n), key=lambda i: secondary_p_values[i])
    adjusted = [None] * n
    running_max = 0.0
    for rank, i in enumerate(order):
        multiplier = n - rank
        candidate = min(secondary_p_values[i] * multiplier, 1.0)
        running_max = max(running_max, candidate)
        adjusted[i] = running_max
    return adjusted


def apply_correction(results: List[ComparisonResult]) -> List[ComparisonResult]:
    """Primary comparisons pass through with adjusted_p == raw_p. Secondary
    comparisons get Holm-Bonferroni adjustment across the secondary family only."""
    primaries = [r for r in results if r.is_primary]
    secondaries = [r for r in results if not r.is_primary]

    adjusted_primaries = [r._replace(adjusted_p=r.raw_p) for r in primaries]

    secondary_p = [r.raw_p for r in secondaries]
    adjusted_p = holm_bonferroni(secondary_p) if secondary_p else []
    adjusted_secondaries = [
        r._replace(adjusted_p=adj) for r, adj in zip(secondaries, adjusted_p)
    ]

    by_label = {r.label: r for r in adjusted_primaries + adjusted_secondaries}
    return [by_label[r.label] for r in results]
