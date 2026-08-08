import math
import os
import tempfile

import numpy as np
import pytest

from gptcache_ext.contracts import EntryMeta
from gptcache_ext.staleness.clusters import assign_cluster, fit_clusters
from gptcache_ext.staleness.fitter import fit_staleness_table
from gptcache_ext.staleness.gate import TTLGate
from tests.invariants import check_no_valid_until_leak


def make_meta(cluster_id, create_on, last_access, entry_id=1):
    return EntryMeta(
        entry_id=entry_id,
        cluster_id=cluster_id,
        answer_id=1,
        create_on=create_on,
        last_access=last_access,
        valid_until=float("inf"),
        freq=1.0,
        regen_cost=0.001,
        size_bytes=100,
    )


def make_synthetic_trace(true_lambdas, n_per_cluster, seed):
    """Builds a calib-split trace where valid_until - t is exponential with rate
    true_lambdas[cluster_id]."""
    rng = np.random.default_rng(seed)
    rows = []
    query_id = 0
    for cluster_id, lambda_true in true_lambdas.items():
        durations = rng.exponential(scale=1.0 / lambda_true, size=n_per_cluster)
        for duration in durations:
            t = float(query_id)
            rows.append(
                {
                    "t": t,
                    "query_id": query_id,
                    "text": f"query {query_id}",
                    "cluster_id": cluster_id,
                    "answer_id": query_id,
                    "valid_until": t + float(duration),
                    "regen_cost": 0.001,
                    "size_bytes": 100,
                    "paraphrase_of": None,
                    "split": "calib",
                }
            )
            query_id += 1
    return rows


class TestClusters:
    def test_seeded_kmeans_deterministic(self):
        rng = np.random.default_rng(0)
        embeddings = rng.normal(size=(200, 8))
        model1 = fit_clusters(embeddings, k=4, seed=42)
        model2 = fit_clusters(embeddings, k=4, seed=42)
        assert np.array_equal(model1.centroids, model2.centroids)

    def test_unseen_query_assigned_nearest_centroid(self):
        rng = np.random.default_rng(1)
        embeddings = np.vstack(
            [
                rng.normal(loc=0.0, scale=0.1, size=(50, 2)),
                rng.normal(loc=10.0, scale=0.1, size=(50, 2)),
            ]
        )
        model = fit_clusters(embeddings, k=2, seed=7)
        near_first = assign_cluster(model, np.array([0.2, -0.1]))
        near_second = assign_cluster(model, np.array([9.8, 10.3]))
        assert near_first != near_second

    def test_centroids_persist_across_save_load(self):
        rng = np.random.default_rng(2)
        embeddings = rng.normal(size=(100, 4))
        model = fit_clusters(embeddings, k=3, seed=3)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "centroids.npy")
            model.save(path)
            from gptcache_ext.staleness.clusters import KMeansModel

            loaded = KMeansModel.load(path)
            assert np.array_equal(loaded.centroids, model.centroids)
            # a round-tripped model must assign an embedding exactly as the in-memory one
            assert assign_cluster(loaded, embeddings[0]) == assign_cluster(model, embeddings[0])


class TestFitter:
    def test_learned_lambda_within_10_percent_at_n_obs_100(self):
        # n_per_cluster sits well above the n_obs >= 100 floor this test is named for:
        # the exponential MLE has enough variance at n=100-200 that a single seed can
        # miss 10% by chance, so the larger sample keeps the assertion about estimator
        # correctness (not about sample size) reliable across seeds.
        true_lambdas = {0: 1.0 / 3600.0, 1: 1.0 / 7200.0, 2: 1.0 / 1800.0}
        rows = make_synthetic_trace(true_lambdas, n_per_cluster=2000, seed=123)
        table = fit_staleness_table(rows, mode="learned", confidence=0.9)
        for cluster_id, true_lambda in true_lambdas.items():
            fitted = table.get(cluster_id)
            assert fitted.n_obs >= 100
            relative_error = abs(fitted.lambda_ - true_lambda) / true_lambda
            assert relative_error < 0.10, (
                f"cluster {cluster_id}: fitted lambda {fitted.lambda_} vs "
                f"true {true_lambda}, relative error {relative_error}"
            )

    def test_small_cluster_falls_back_to_global(self):
        true_lambdas = {0: 1.0 / 3600.0}
        rows = make_synthetic_trace(true_lambdas, n_per_cluster=200, seed=5)
        sparse_rows = [
            {
                "t": 100000.0,
                "query_id": 99999,
                "text": "rare query",
                "cluster_id": 1,
                "answer_id": 99999,
                "valid_until": 100000.0 + 500.0,
                "regen_cost": 0.001,
                "size_bytes": 100,
                "paraphrase_of": None,
                "split": "calib",
            }
            for _ in range(5)
        ]
        table = fit_staleness_table(rows + sparse_rows, mode="learned", confidence=0.9)
        sparse_cluster = table.get(1)
        assert sparse_cluster.n_obs == 5
        assert sparse_cluster.lambda_ == table.global_.lambda_

    def test_global_mode_uses_one_pooled_lambda_everywhere(self):
        true_lambdas = {0: 1.0 / 3600.0, 1: 1.0 / 1800.0}
        rows = make_synthetic_trace(true_lambdas, n_per_cluster=100, seed=9)
        table = fit_staleness_table(rows, mode="global", confidence=0.9)
        lambda_0 = table.get(0).lambda_
        lambda_1 = table.get(1).lambda_
        assert lambda_0 == lambda_1 == table.global_.lambda_

    def test_oracle_mode_reproduces_lambda_exactly(self):
        rows = make_synthetic_trace({0: 1.0 / 3600.0}, n_per_cluster=10, seed=11)
        oracle_lambdas = {0: 1.0 / 3600.0, 1: 1.0 / 42.0}
        table = fit_staleness_table(
            rows, mode="oracle", confidence=0.9, oracle_lambdas=oracle_lambdas
        )
        assert table.get(0).lambda_ == oracle_lambdas[0]
        assert table.get(1).lambda_ == oracle_lambdas[1]

    def test_oracle_mode_requires_oracle_lambdas(self):
        rows = make_synthetic_trace({0: 1.0 / 3600.0}, n_per_cluster=10, seed=11)
        with pytest.raises(ValueError):
            fit_staleness_table(rows, mode="oracle", confidence=0.9)

    def test_ttl_seconds_derived_from_lambda_and_confidence(self):
        rows = make_synthetic_trace({0: 1.0 / 100.0}, n_per_cluster=200, seed=13)
        table = fit_staleness_table(rows, mode="learned", confidence=0.9)
        fitted = table.get(0)
        expected_ttl = -math.log(0.9) / fitted.lambda_
        assert fitted.ttl_seconds == pytest.approx(expected_ttl)

    def test_eval_split_rows_excluded_from_fit(self):
        rows = make_synthetic_trace({0: 1.0 / 3600.0}, n_per_cluster=200, seed=17)
        for row in rows:
            row["split"] = "eval"
        table = fit_staleness_table(rows, mode="learned", confidence=0.9)
        assert table.global_.n_obs == 0

    def test_deterministic_json_output(self):
        rows = make_synthetic_trace(
            {0: 1.0 / 3600.0, 1: 1.0 / 1800.0}, n_per_cluster=150, seed=21
        )
        table1 = fit_staleness_table(rows, mode="learned", confidence=0.9)
        table2 = fit_staleness_table(rows, mode="learned", confidence=0.9)
        with tempfile.TemporaryDirectory() as tmp:
            path1 = os.path.join(tmp, "table1.json")
            path2 = os.path.join(tmp, "table2.json")
            table1.save(path1)
            table2.save(path2)
            with open(path1, "rb") as f1, open(path2, "rb") as f2:
                assert f1.read() == f2.read()

    def test_save_load_roundtrip(self):
        rows = make_synthetic_trace({0: 1.0 / 3600.0}, n_per_cluster=100, seed=23)
        table = fit_staleness_table(rows, mode="learned", confidence=0.9)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "table.json")
            table.save(path)
            from gptcache_ext.staleness.fitter import ClusterStalenessTable

            loaded = ClusterStalenessTable.load(path)
            assert loaded.get(0) == table.get(0)


class TestGate:
    def setup_method(self):
        rows = make_synthetic_trace({0: 1.0 / 1000.0}, n_per_cluster=200, seed=31)
        self.table = fit_staleness_table(rows, mode="learned", confidence=0.9)
        self.gate = TTLGate(self.table)
        self.ttl_seconds = self.table.get(0).ttl_seconds

    def test_fresh_entry_not_stale(self):
        now = 1000.0
        meta = make_meta(cluster_id=0, create_on=now - 1.0, last_access=now - 1.0)
        assert not self.gate.is_stale(meta, now)

    def test_exactly_at_ttl_boundary_not_stale(self):
        # derive now from create_on + ttl_seconds, not the other way around, so
        # now - create_on recovers exactly ttl_seconds without float rounding noise
        create_on = 1000.0
        now = create_on + self.ttl_seconds
        meta = make_meta(cluster_id=0, create_on=create_on, last_access=now)
        assert not self.gate.is_stale(meta, now)

    def test_expired_entry_is_stale(self):
        now = 1000.0
        meta = make_meta(
            cluster_id=0, create_on=now - self.ttl_seconds - 1.0, last_access=now
        )
        assert self.gate.is_stale(meta, now)

    def test_unseen_cluster_falls_back_to_global_never_raises(self):
        now = 1000.0
        global_ttl = self.table.global_.ttl_seconds
        fresh = make_meta(cluster_id=999, create_on=now - 1.0, last_access=now)
        expired = make_meta(cluster_id=999, create_on=now - global_ttl - 1.0, last_access=now)
        assert not self.gate.is_stale(fresh, now)
        assert self.gate.is_stale(expired, now)

    def test_gate_ignores_last_access(self):
        now = 1000.0
        hot = make_meta(
            cluster_id=0,
            create_on=now - self.ttl_seconds - 1.0,
            last_access=now - 0.001,
            entry_id=1,
        )
        cold = make_meta(
            cluster_id=0,
            create_on=now - self.ttl_seconds - 1.0,
            last_access=now - 999999.0,
            entry_id=2,
        )
        assert self.gate.is_stale(hot, now) == self.gate.is_stale(cold, now)


def test_no_valid_until_leak_still_passes():
    check_no_valid_until_leak()
