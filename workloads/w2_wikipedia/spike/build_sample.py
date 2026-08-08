"""Build a schema-conformant sample trace from the cached Wikipedia revisions
and the automatic invalidation rule.

Each row represents one "query" for a SQuAD answer at the timestamp of a
Wikipedia revision that touched the page. valid_until is set to the timestamp
of the next revision that changed the answer sentence per the automatic rule
in detect_invalidations.py, or infinity if no later revision changes it.

This sample exists to demonstrate that the trace schema the harness consumes is
mechanically producible from this data source. It is explicitly NOT proposed as
reliable ground truth: the hand-labeling exercise in hand_labels.py finds the
automatic rule agrees with human judgment only 40% of the time, almost entirely because
sentence-level diffing catches copyedits and infobox/template artifacts that
do not change the underlying fact. See docs/w2-feasibility.md.
"""
import datetime
import json
from pathlib import Path

SPIKE_DIR = Path(__file__).parent

# Standard JSON has no Infinity literal, so "never stale" is encoded as this
# far-future sentinel timestamp (year 9999) rather than float("inf"), which
# json.dumps would write as the non-standard token "Infinity".
NEVER_STALE = 253402300799.0


def to_unix(timestamp):
    return datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    ).timestamp()


TARGET_ROWS = 200


def build_rows():
    questions = json.loads((SPIKE_DIR / "questions.json").read_text())
    rows = []
    for cluster_id, question in enumerate(questions):
        title = question["title"]
        revisions = json.loads((SPIKE_DIR / "revisions_cache" / f"{title}.json").read_text())
        sentences = [r["sentence"] for r in revisions]

        for i, revision in enumerate(revisions):
            if sentences[i] is None:
                continue
            valid_until = NEVER_STALE
            for j in range(i + 1, len(revisions)):
                if sentences[j] != sentences[i]:
                    valid_until = to_unix(revisions[j]["timestamp"])
                    break
            rows.append({
                "t": to_unix(revision["timestamp"]),
                "query_id": len(rows),
                "text": question["question"],
                "cluster_id": cluster_id,
                "answer_id": cluster_id,
                "valid_until": valid_until,
                "regen_cost": 0.001,
                "size_bytes": len(sentences[i].encode("utf-8")),
                "paraphrase_of": None,
                "split": None,
            })
    rows.sort(key=lambda r: r["t"])

    if len(rows) > TARGET_ROWS:
        stride = len(rows) / TARGET_ROWS
        rows = [rows[int(i * stride)] for i in range(TARGET_ROWS)]

    cut = int(len(rows) * 0.3)
    for i, row in enumerate(rows):
        row["query_id"] = i
        row["split"] = "calib" if i < cut else "eval"
    return rows


def main():
    rows = build_rows()
    out_path = SPIKE_DIR / "sample.jsonl"
    with out_path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
