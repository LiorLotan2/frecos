"""A small, fully deterministic trace and stub policy set used for the bench-smoke
target, CI, and the sample CSV/JSON under benchmarks/samples/. This is not the W1 workload
generator - it is a fixed, hand-built trace just big enough to
exercise hits, misses, stale hits, and false hits through the harness.

The gate is disabled here on purpose: stale_hit_rate is only interesting to report when
nothing in the serve path is catching staleness, which is the situation stock GPTCache
(and any cache without a staleness gate) is actually in.
"""
import argparse
import json

from gptcache_ext.config import Config
from gptcache_ext.contracts import ClusterStaleness

from benchmarks.harness import CSV_COLUMNS, run_harness, write_csv_row

SEED = 7
RUN_ID = "smoke-w1-lru-seed7"


class SmokeNullGate:
    def is_stale(self, meta, now):
        return False


class SmokeLRUPolicy:
    def value(self, meta, now):
        return meta.last_access

    @staticmethod
    def _sort_key(meta):
        return (meta.last_access, meta.create_on, meta.entry_id)

    def select_victim(self, metas, now):
        return min(metas, key=self._sort_key).entry_id


class SmokeGlobalStalenessTable:
    def get(self, cluster_id):
        return ClusterStaleness(
            cluster_id=cluster_id, lambda_=0.0, ttl_seconds=float("inf"), n_obs=0
        )


def build_smoke_trace():
    """40 eval-split rows, no randomness. Pattern, by row index i (0-based):
    - text cycles through q0..q9 (10 distinct texts, cluster_id = index % 3).
    - rows 0-9 are the first-ever sighting of each text and set valid_until = t + 5,
      short enough that it has already passed by the time the text is next queried
      20 seconds later.
    - rows 10-19 repeat q0..q9. The entry is still in cache (cache_size_entries=20,
      bigger than the working set, so nothing evicts it), the gate is disabled so
      decide() still returns HIT, and serve_time > valid_until: these are the
      ground-truth stale hits the metric is meant to catch.
    - rows 20-21 repeat q0 and q1 again but the query's own answer_id has drifted
      (the fact changed), while the cached entry still carries the old answer_id:
      false hits.
    - rows 22-39 are the same 10 texts cycling twice more, with valid_until = inf,
      so they are plain (non-stale, non-false) hits.
    """
    rows = []
    t = 1_700_000_000.0
    for i in range(40):
        qi = i % 10
        text = f"q{qi}"
        cluster_id = qi % 3
        answer_id = qi
        if i in (20, 21):
            answer_id = qi + 100  # ground truth drifted; cached entry still says qi
        valid_until = t + 5.0 if i < 10 else float("inf")
        rows.append(
            dict(
                t=t,
                query_id=i,
                text=text,
                cluster_id=cluster_id,
                answer_id=answer_id,
                valid_until=valid_until,
                regen_cost=0.002,
                size_bytes=600,
                paraphrase_of=None,
                split="eval",
            )
        )
        t += 2.0
    return rows


def build_smoke_config():
    return Config(
        gate_enabled=False,
        eviction_policy="LRU",
        cache_size_entries=20,
        cluster_count_k=3,
        ttl_confidence=0.9,
        lambda_source="none",
        seed=SEED,
    )


def run_smoke():
    trace = build_smoke_trace()
    config = build_smoke_config()
    return run_harness(
        trace,
        config,
        seed=SEED,
        gate=SmokeNullGate(),
        eviction_policy=SmokeLRUPolicy(),
        staleness_table=SmokeGlobalStalenessTable(),
        workload="w1",
        run_id=RUN_ID,
    )


def main():
    parser = argparse.ArgumentParser(description="Run the smoke benchmark and print the result.")
    parser.add_argument("--csv", help="append the row to this CSV file")
    parser.add_argument("--json", help="write the row as JSON to this file")
    args = parser.parse_args()

    row = run_smoke()

    if args.csv:
        write_csv_row(row, args.csv)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(row, f, indent=2)

    print(",".join(str(row[c]) for c in CSV_COLUMNS))


if __name__ == "__main__":
    main()
