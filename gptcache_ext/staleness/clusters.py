"""Seeded k-means over query embeddings, and the single place cluster ids get assigned.

This module is the only source of truth for cluster identity in the project. The
eviction policy and the staleness gate both consume cluster_id from EntryMeta, which
is populated by assigning a query's embedding here at write time. Nothing downstream
should ever run its own clustering or nearest-centroid logic.
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class KMeansModel:
    centroids: np.ndarray  # shape (k, dim)

    def assign(self, embedding: np.ndarray) -> int:
        distances = np.linalg.norm(self.centroids - embedding, axis=1)
        return int(np.argmin(distances))

    def assign_many(self, embeddings: np.ndarray) -> np.ndarray:
        distances = np.linalg.norm(
            embeddings[:, None, :] - self.centroids[None, :, :], axis=2
        )
        return np.argmin(distances, axis=1)

    def save(self, path: str) -> None:
        np.save(path, self.centroids)

    @classmethod
    def load(cls, path: str) -> "KMeansModel":
        return cls(centroids=np.load(path))


def assign_cluster(model: KMeansModel, embedding: np.ndarray) -> int:
    return model.assign(embedding)


def fit_clusters(embeddings: np.ndarray, k: int, seed: int, max_iter: int = 100) -> KMeansModel:
    """Lloyd's algorithm, seeded. embeddings has shape (n, dim), n >= k."""
    rng = np.random.default_rng(seed)
    n = embeddings.shape[0]
    initial_indices = rng.choice(n, size=k, replace=False)
    centroids = embeddings[initial_indices].copy()

    for _ in range(max_iter):
        distances = np.linalg.norm(
            embeddings[:, None, :] - centroids[None, :, :], axis=2
        )
        assignments = np.argmin(distances, axis=1)

        new_centroids = centroids.copy()
        for cluster_id in range(k):
            members = embeddings[assignments == cluster_id]
            if len(members) > 0:
                new_centroids[cluster_id] = members.mean(axis=0)
            # empty cluster keeps its previous centroid rather than being
            # reseeded, since a course-project workload is small enough that
            # reseeding logic would add complexity with no observable benefit

        if np.allclose(new_centroids, centroids):
            centroids = new_centroids
            break
        centroids = new_centroids

    return KMeansModel(centroids=centroids)
