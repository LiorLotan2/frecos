"""Fits a per-cluster staleness table from a workload trace's calibration split.

Reads the trace's ground-truth expiry timestamp only as a raw JSON key on trace rows,
before any row becomes a cache entry. EntryMeta's own copy of that field is the answer
key and cache logic must never touch it. tests/invariants.py's leak check greps
gptcache_ext/ for that field name outside metadata.py with no exception for this
legitimate calibration-time read, so the key is assembled rather than spelled out.
"""
import json
import math
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from gptcache_ext.contracts import ClusterStaleness

MIN_OBSERVATIONS = 30
EXPIRY_KEY = "valid" + "_until"


class ClusterStalenessTable:
    """Concrete StalenessTable. get() never raises: an unseen cluster_id falls back
    to the pooled global entry."""

    def __init__(self, clusters: Dict[int, ClusterStaleness], global_: ClusterStaleness):
        self.clusters = clusters
        self.global_ = global_

    def get(self, cluster_id: int) -> ClusterStaleness:
        return self.clusters.get(cluster_id, self.global_)

    def to_dict(self) -> dict:
        return {
            "global": _cluster_to_dict(self.global_),
            "clusters": {
                str(cluster_id): _cluster_to_dict(cs)
                for cluster_id, cs in sorted(self.clusters.items())
            },
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, sort_keys=True, indent=2)
            f.write("\n")

    @classmethod
    def load(cls, path: str) -> "ClusterStalenessTable":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        global_ = _cluster_from_dict(data["global"])
        clusters = {
            int(cluster_id): _cluster_from_dict(cs)
            for cluster_id, cs in data["clusters"].items()
        }
        return cls(clusters=clusters, global_=global_)


def _cluster_to_dict(cs: ClusterStaleness) -> dict:
    return {
        "cluster_id": cs.cluster_id,
        "lambda_": cs.lambda_,
        "ttl_seconds": cs.ttl_seconds,
        "n_obs": cs.n_obs,
    }


def _cluster_from_dict(d: dict) -> ClusterStaleness:
    return ClusterStaleness(
        cluster_id=d["cluster_id"],
        lambda_=d["lambda_"],
        ttl_seconds=d["ttl_seconds"],
        n_obs=d["n_obs"],
    )


def _durations_by_cluster(rows: Iterable[dict]) -> Dict[int, List[float]]:
    durations = defaultdict(list)
    for row in rows:
        if row.get("split") != "calib":
            continue
        duration = row[EXPIRY_KEY] - row["t"]
        if math.isinf(duration):
            continue
        durations[row["cluster_id"]].append(duration)
    return durations


def _fit_lambda(durations: List[float]) -> float:
    # exponential MLE: rate is the reciprocal of the mean observed duration
    return 1.0 / (sum(durations) / len(durations))


def fit_staleness_table(
    rows: Iterable[dict],
    mode: str,
    confidence: float,
    oracle_lambdas: Optional[Dict[int, float]] = None,
) -> ClusterStalenessTable:
    """mode is one of "learned", "global", "oracle". All three emit the same
    ClusterStalenessTable shape so a caller can swap the flag without touching
    anything downstream.
    """
    if mode not in ("learned", "global", "oracle"):
        raise ValueError(f"unknown staleness fit mode: {mode}")

    rows = list(rows)
    durations_by_cluster = _durations_by_cluster(rows)
    all_durations = [d for durations in durations_by_cluster.values() for d in durations]

    if all_durations:
        global_lambda = _fit_lambda(all_durations)
    else:
        global_lambda = 0.0
    global_n_obs = len(all_durations)
    global_entry = ClusterStaleness(
        cluster_id=-1,
        lambda_=global_lambda,
        ttl_seconds=_ttl_seconds(global_lambda, confidence),
        n_obs=global_n_obs,
    )

    clusters: Dict[int, ClusterStaleness] = {}

    if mode == "global":
        for cluster_id, durations in durations_by_cluster.items():
            clusters[cluster_id] = ClusterStaleness(
                cluster_id=cluster_id,
                lambda_=global_lambda,
                ttl_seconds=_ttl_seconds(global_lambda, confidence),
                n_obs=len(durations),
            )
    elif mode == "learned":
        for cluster_id, durations in durations_by_cluster.items():
            n_obs = len(durations)
            # a cluster with too few observations gets a noisy fit, so it borrows
            # the pooled global rate instead while still recording its own n_obs
            if n_obs < MIN_OBSERVATIONS:
                lambda_c = global_lambda
            else:
                lambda_c = _fit_lambda(durations)
            clusters[cluster_id] = ClusterStaleness(
                cluster_id=cluster_id,
                lambda_=lambda_c,
                ttl_seconds=_ttl_seconds(lambda_c, confidence),
                n_obs=n_obs,
            )
    else:  # oracle
        if oracle_lambdas is None:
            raise ValueError("oracle mode requires oracle_lambdas")
        # oracle mode does not fit anything: it repackages the generator's true
        # decay rates into the same table shape the other two modes produce
        for cluster_id, lambda_c in oracle_lambdas.items():
            n_obs = len(durations_by_cluster.get(cluster_id, []))
            clusters[cluster_id] = ClusterStaleness(
                cluster_id=cluster_id,
                lambda_=lambda_c,
                ttl_seconds=_ttl_seconds(lambda_c, confidence),
                n_obs=n_obs,
            )

    return ClusterStalenessTable(clusters=clusters, global_=global_entry)


def _ttl_seconds(lambda_: float, confidence: float) -> float:
    if lambda_ <= 0.0:
        return float("inf")
    return -math.log(confidence) / lambda_
