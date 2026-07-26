"""Adjusted Rand Index between a learned cluster assignment and the generator's true
cluster labels, hand-rolled the same way this project hand-rolls Mann-Whitney U
(scipy/sklearn are not available in this sandbox).
"""
from collections import Counter
from math import comb


def adjusted_rand_index(labels_true, labels_pred) -> float:
    """Standard ARI: 1.0 for a perfect match (up to label permutation), ~0.0 for a
    random assignment, negative for worse than random. Sizes of labels_true and
    labels_pred must match; every pairwise co-membership is compared implicitly via
    the contingency table, so this is O(n_true_clusters * n_pred_clusters), not O(n^2).
    """
    n = len(labels_true)
    if n == 0:
        return 0.0

    contingency = Counter(zip(labels_true, labels_pred))
    row_sums = Counter()
    col_sums = Counter()
    for (t, p), count in contingency.items():
        row_sums[t] += count
        col_sums[p] += count

    sum_comb_c = sum(comb(count, 2) for count in contingency.values())
    sum_comb_rows = sum(comb(count, 2) for count in row_sums.values())
    sum_comb_cols = sum(comb(count, 2) for count in col_sums.values())
    total_comb = comb(n, 2)

    expected_index = (sum_comb_rows * sum_comb_cols) / total_comb if total_comb else 0.0
    max_index = (sum_comb_rows + sum_comb_cols) / 2.0
    denominator = max_index - expected_index

    if denominator == 0:
        return 1.0 if sum_comb_c == max_index else 0.0

    return (sum_comb_c - expected_index) / denominator
