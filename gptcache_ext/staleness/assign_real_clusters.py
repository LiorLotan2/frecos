"""Replaces a trace's oracle-perfect cluster_id with a real, embedding-based cluster
assignment: embed every distinct query text, fit k-means on the calibration split's
embeddings only, then assign every row (calibration and eval) to its nearest centroid.

The generator's true cluster_id is preserved under `true_cluster_id` on every row, used
only to report cluster-assignment accuracy (adjusted Rand index) -- never consumed by
the gate or eviction, which read `cluster_id` and see only the learned assignment.
"""
from typing import List

import numpy as np

from gptcache_ext.staleness.cluster_accuracy import adjusted_rand_index
from gptcache_ext.staleness.clusters import fit_clusters


def assign_real_clusters(rows: List[dict], embedder, n_clusters: int, seed: int) -> float:
    """Mutates rows in place: adds `true_cluster_id` (the generator's label) and
    overwrites `cluster_id` with the learned assignment. Returns the adjusted Rand
    index between the two labelings over the full trace, as a measure of how much the
    embedding-and-k-means pipeline recovered of the true cluster structure.
    """
    for row in rows:
        row["true_cluster_id"] = row["cluster_id"]

    distinct_texts = sorted({row["text"] for row in rows})
    embeddings_by_text = {
        text: vec for text, vec in zip(distinct_texts, embedder.embed_many(distinct_texts))
    }

    calib_rows = [r for r in rows if r["split"] == "calib"]
    calib_embeddings = np.stack([embeddings_by_text[r["text"]] for r in calib_rows])
    model = fit_clusters(calib_embeddings, k=n_clusters, seed=seed)

    for row in rows:
        row["cluster_id"] = model.assign(embeddings_by_text[row["text"]])

    true_labels = [row["true_cluster_id"] for row in rows]
    learned_labels = [row["cluster_id"] for row in rows]
    return adjusted_rand_index(true_labels, learned_labels)
