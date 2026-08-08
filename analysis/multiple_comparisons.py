"""Holm-Bonferroni correction over the family of Mann-Whitney comparisons this project
reports.

COMPARISONS enumerates that family explicitly, so its membership is checkable rather than
implied: each entry names the committed results/*/results.csv it is computed from, the two
arms it contrasts, and the metric column it scores. main() recomputes every U statistic,
rank-biserial r and raw p from those CSVs through analysis/stats.py -- the single
Mann-Whitney implementation in this project -- and prints raw and adjusted p side by side,
so every number in the table is regenerable from the committed data rather than
transcribed.

Two comparisons are designated primary and are reported uncorrected, since a primary
comparison is tested once, on its own account. Every other entry is secondary and is
corrected against the rest of the secondary family only.

scipy is not available in this sandbox (the same reason analysis/stats.py hand-rolls
Mann-Whitney U), so the step-down Holm procedure below is a plain implementation rather
than a library call.

Run with: python3 analysis/multiple_comparisons.py, or `make multiple-comparisons`.
"""
from typing import List, NamedTuple

from common import load_csv, REPO_ROOT
from stats import mann_whitney_u

ALPHA = 0.05

# The seed count every experiment behind these comparisons runs at. Used only to report
# the smallest p analysis/stats.py's normal approximation can return at this sample size.
SEEDS_PER_ARM = 5


class Comparison(NamedTuple):
    """One two-sample comparison: which results.csv, which two arms, which metric.

    arm_a and arm_b are run_id prefixes (a run_id with its trailing -seed<N> removed), so
    the arm an entry points at is greppable in the CSV itself. Order matters: U_a and the
    sign of r are reported for arm_a against arm_b.
    """
    tag: str
    label: str
    source: str
    arm_a: str
    arm_b: str
    metric: str
    is_primary: bool = False


COMPARISONS = (
    Comparison("P1", "brackets learned vs global", "results/brackets/results.csv",
               "brackets-w1-learned", "brackets-w1-global", "stale_hit_rate",
               is_primary=True),
    Comparison("P2", "ablation row 2 floor vs row 4", "results/ablation/results.csv",
               "ablation-w1-row2_lfu", "ablation-w1-row4_gate_lfu", "stale_hit_rate",
               is_primary=True),
    Comparison("S1", "brackets learned vs oracle", "results/brackets/results.csv",
               "brackets-w1-learned", "brackets-w1-oracle", "stale_hit_rate"),
    Comparison("S2", "Weibull learned vs global",
               "results/brackets/misspecified/results.csv",
               "brackets-misspecified-w1-learned", "brackets-misspecified-w1-global",
               "stale_hit_rate"),
    Comparison("S3", "Weibull learned vs oracle",
               "results/brackets/misspecified/results.csv",
               "brackets-misspecified-w1-learned", "brackets-misspecified-w1-oracle",
               "stale_hit_rate"),
    Comparison("S4", "mixture learned vs global",
               "results/brackets/mixture/results.csv",
               "brackets-mixture-w1-learned", "brackets-mixture-w1-global",
               "stale_hit_rate"),
    Comparison("S5", "mixture learned vs oracle",
               "results/brackets/mixture/results.csv",
               "brackets-mixture-w1-learned", "brackets-mixture-w1-oracle",
               "stale_hit_rate"),
    Comparison("S6", "cost-aware FreCoS vs LFU",
               "results/cost_aware_eviction/results.csv",
               "cost-aware-w1-row1_frecos", "cost-aware-w1-row2_lfu", "cost_saved_usd"),
    Comparison("S7", "cost-aware FreCoS vs LRU",
               "results/cost_aware_eviction/results.csv",
               "cost-aware-w1-row1_frecos", "cost-aware-w1-row3_lru", "cost_saved_usd"),
    Comparison("S8", "cost-aware FreCoS vs LRU",
               "results/cost_aware_eviction/results.csv",
               "cost-aware-w1-row1_frecos", "cost-aware-w1-row3_lru", "stale_hit_rate"),
    Comparison("S9", "cost-aware LRU vs LFU",
               "results/cost_aware_eviction/results.csv",
               "cost-aware-w1-row3_lru", "cost-aware-w1-row2_lfu", "stale_hit_rate"),
    Comparison("S10", "ttl confidence 0.95 vs 0.99",
               "results/sweeps/ttl_confidence/results.csv",
               "sweep-ttl_confidence-0.95", "sweep-ttl_confidence-0.99",
               "useful_hit_rate"),
)

HEADER = "{:<3}  {:<30}  {:<15}  {:>6}  {:>6}  {:>8}  {:>16}  {}".format(
    "id", "comparison", "metric", "U_a", "r", "raw p", "adj p", "holds")
RULE = "  ".join("-" * width for width in (3, 30, 15, 6, 6, 8, 16, 5))
ROW = ("{tag:<3}  {label:<30}  {metric:<15}  {u_a:>6.1f}  {r:>+6.3f}  {raw_p:>8.6f}  "
       "{adjusted:>16}  {holds}")

PRIMARY_ADJUSTED = "exempt (primary)"


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


def arm_of(row):
    """Arm identity of a run: its run_id with the trailing -seed<N> removed."""
    return row["run_id"].rsplit("-seed", 1)[0]


def arm_values(rows, arm, metric):
    """The per-seed values of `metric` for one arm, in the CSV's own row order."""
    return [float(row[metric]) for row in rows if arm_of(row) == arm]


def run_comparisons():
    """Compute (Comparison, MannWhitneyResult) for every entry in COMPARISONS."""
    by_source = {}
    tested = []
    for comparison in COMPARISONS:
        if comparison.source not in by_source:
            by_source[comparison.source] = load_csv(REPO_ROOT / comparison.source)
        rows = by_source[comparison.source]
        tested.append((comparison, mann_whitney_u(
            arm_values(rows, comparison.arm_a, comparison.metric),
            arm_values(rows, comparison.arm_b, comparison.metric),
        )))
    return tested, sorted(by_source)


def main():
    tested, sources = run_comparisons()
    corrected = apply_correction([
        ComparisonResult(label=c.tag, raw_p=mw.p_value, is_primary=c.is_primary)
        for c, mw in tested
    ])
    secondary = [r for r in corrected if not r.is_primary]
    primary = [r for r in corrected if r.is_primary]

    print("Holm-Bonferroni over the Mann-Whitney family reported for this project, "
          "alpha = {}".format(ALPHA))
    print("{} primary comparisons reported uncorrected, {} secondary comparisons "
          "corrected together".format(len(primary), len(secondary)))
    print()
    print(HEADER)
    print(RULE)
    for (comparison, mw), result in zip(tested, corrected):
        print(ROW.format(
            tag=comparison.tag,
            label=comparison.label,
            metric=comparison.metric,
            u_a=mw.u_a,
            r=mw.r,
            raw_p=mw.p_value,
            adjusted=(PRIMARY_ADJUSTED if comparison.is_primary
                      else "{:.6f}".format(result.adjusted_p)),
            holds="yes" if result.adjusted_p <= ALPHA else "no",
        ))
    print()

    held = [r for r in secondary if r.adjusted_p <= ALPHA]
    print("Smallest adjusted p in the secondary family: {:.6f}. {} of {} secondary "
          "comparisons hold at alpha = {}.".format(
              min(r.adjusted_p for r in secondary), len(held), len(secondary), ALPHA))
    for result in primary:
        print("Primary {} is exempt from correction and {} on its raw p = {:.6f}.".format(
            result.label,
            "holds" if result.raw_p <= ALPHA else "does not hold",
            result.raw_p))

    floor = mann_whitney_u(range(SEEDS_PER_ARM),
                           range(SEEDS_PER_ARM, 2 * SEEDS_PER_ARM)).p_value
    print("Complete separation at n_a = n_b = {} gives p = {:.6f}, the smallest two-sided "
          "p analysis/stats.py's".format(SEEDS_PER_ARM, floor))
    print("normal approximation can return, so {:.6f} x {} = {:.6f} is the smallest "
          "adjusted p a family of".format(floor, len(secondary), floor * len(secondary)))
    print("this size can reach: no {}-member secondary family at {} seeds per arm can "
          "clear alpha = {}.".format(len(secondary), SEEDS_PER_ARM, ALPHA))
    print()
    print("Recomputed from: {}".format(", ".join(sources)))


if __name__ == "__main__":
    main()
