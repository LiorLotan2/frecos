"""Walk each question's cached revision history and apply the automatic
invalidation rule: an answer generated from revision r becomes invalid at the
first later revision whose plain-text answer sentence differs from r's.

Because the cached sentence (see fetch_revisions.py) is already extracted from
plain text with refs, templates, and markup stripped, a diff limited to
citations or formatting produces an identical sentence and is correctly not
flagged.

Writes candidate_pairs.json: one entry per (question, revision transition)
where the answer sentence text changed, for hand-labeling.
"""
import json
from pathlib import Path

SPIKE_DIR = Path(__file__).parent


def main():
    questions = json.loads((SPIKE_DIR / "questions.json").read_text())
    pairs = []
    for question in questions:
        title = question["title"]
        answer = question["answer"]
        revisions = json.loads((SPIKE_DIR / "revisions_cache" / f"{title}.json").read_text())

        sentences = [r["sentence"] for r in revisions]
        for i in range(1, len(revisions)):
            if sentences[i] != sentences[i - 1]:
                pairs.append({
                    "title": title,
                    "answer": answer,
                    "question": question["question"],
                    "from_revid": revisions[i - 1]["revid"],
                    "to_revid": revisions[i]["revid"],
                    "from_timestamp": revisions[i - 1]["timestamp"],
                    "to_timestamp": revisions[i]["timestamp"],
                    "sentence_before": sentences[i - 1],
                    "sentence_after": sentences[i],
                    "rule_verdict": "invalidating",
                })

    (SPIKE_DIR / "candidate_pairs.json").write_text(json.dumps(pairs, indent=1))
    print(f"{len(pairs)} candidate invalidating transitions across {len(questions)} questions")


if __name__ == "__main__":
    main()
