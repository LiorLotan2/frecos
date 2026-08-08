# W2 Wikipedia feasibility spike

**Recommendation: cut.** A Wikipedia-derived workload (W2) needs an automatic rule that
decides when a cached answer stopped being correct, and that rule has to agree with human
judgment before it can serve as staleness ground truth. The bar set in advance was 80%
agreement. Measured agreement is 40%, so W2 is cut and the evaluation proceeds on W1
only. The resulting external-validity limitation is stated in the report's Discussion.

## What was tried

30 questions were sampled from SQuAD 2.0 dev (`dev-v2.0.json`, the public
`rajpurkar/SQuAD-explorer` release). SQuAD was chosen over Natural Questions and
TriviaQA because its answers are annotated as exact spans inside a given paragraph of
a named Wikipedia article, which is exactly what a sentence-level invalidation rule
needs; NQ and TriviaQA answers are typically free text matched against the open web,
without a pinned paragraph to track through revisions. Candidate questions were
filtered to those with a short (<=6 word), unique, capitalized-or-numeric answer
string inside a single sentence under 220 characters, then deduplicated to one
question per article, to keep each case simple enough to hand-verify.

For each of the 30 articles, up to 60 revisions were pulled from the Wikipedia REST
API (`action=query&prop=revisions&rvslots=main`, full wikitext per revision).
Wikitext was stripped to plain text with a small regex-based converter
(`wikitext.py`; not a full parser, deliberately) and split into sentences, and the
sentence containing the answer string was located per revision. Only
`{revid, timestamp, sentence}` is cached locally under `revisions_cache/` (full
wikitext for every revision would be ~150KB per revision, too large to commit for
a spike), so nothing downstream depends on the live API.

## The invalidation rule as implemented

The rule as specified: **the answer generated from revision r becomes invalid at the
timestamp of the next revision whose extracted answer sentence differs (as
plain text) from r's.** Revisions where the extracted sentence is byte-identical do
not invalidate. This is implemented in `detect_invalidations.py` and applied over the
cached revision history in `build_sample.py`.

## Hand-labeling and agreement

20 (answer, revision-pair) cases were pulled: 12 that the automatic rule flagged as
invalidating (from `candidate_pairs.json`) and 8 that it flagged as non-invalidating
(sampled from the ~1,400 same-sentence transitions). Each case was read by hand,
comparing the actual wikitext diff against whether the SQuAD answer's correctness
plausibly changed. Full case list and reasoning: `workloads/w2_wikipedia/spike/hand_labels.py`.

**Agreement: 8/20 = 40%.** All 12 disagreements are on the "rule said invalidating"
side, and all 8 "rule said non-invalidating" cases were confirmed correct. Every one
of the 12 false positives has the same structure: the *sentence* the answer sits in
changed, but the *clause containing the answer* did not. Patterns seen:

- Copyedits and grammar fixes elsewhere in the sentence (comma placement, "found out"
  to "found", "before" to "earlier").
- Terminology or spelling swaps unrelated to the queried fact ("Native American" to
  "Indigenous", "Kaffa" to "Caffa", "Welsh" to "British" describing Donald Davies).
- Infobox/template text bleeding into the extracted "sentence" when a template was
  inserted or reordered near the answer, an artifact of the plain-text converter, not
  a real edit near the answer.
- A new sentence inserted earlier in the same paragraph, which the first-match
  sentence extractor then returns instead of the original defining sentence, even
  though the original sentence is unchanged and still present.

A follow-up check narrowed the comparison to an 11-word window centered on the answer
span, rather than the whole sentence. That mechanically fixes 6 of the 12 false
positives (the ones where the answer's local context is untouched) but does not
touch the template-leakage or paragraph-reordering artifacts, which are extraction
bugs in the plain-text converter rather than a comparison-window problem. Getting
those right needs a real wikitext-to-prose renderer (e.g. via the Wikipedia Parsoid
API) instead of the regex stripper used here, plus paragraph-alignment across
revisions instead of first-match sentence lookup.

## What a working loader would still need

Bringing the rule closer to 80% agreement would need, at minimum: Parsoid-based rendering
instead of regex stripping, paragraph-level alignment across revisions instead of
sentence first-match, and a fresh hand-labeled sample to confirm the fix generalizes past
these 30 articles. Only then could a full workload loader be built against it, with API
pagination, retries and a local snapshot cache.

The reason to cut rather than continue is not the engineering volume. It is that 40% is
the agreement of the rule as specified (whole sentence, no window, no Parsoid). The
improved version is a different, unvalidated rule, so it would need its own agreement
measurement before any workload could rest on it, and that measurement is a second
study rather than a fix.

## What ships from this spike

- `workloads/w2_wikipedia/spike/questions.json`: the 30 SQuAD questions/answers/pages.
- `workloads/w2_wikipedia/spike/revisions_cache/`: cached revision history for those
  30 pages (offline, reproducible).
- `workloads/w2_wikipedia/spike/wikitext.py`, `detect_invalidations.py`,
  `build_sample.py`: the pipeline that turns cached revisions into a schema-conformant
  trace.
- `workloads/w2_wikipedia/spike/hand_labels.py`: the 20 hand-labeled cases and the
  agreement check (`python3 hand_labels.py` prints 8/20 = 40%).
- `workloads/w2_wikipedia/spike/sample.jsonl`: 200 rows in the same trace schema the W1
  generator emits, built from the rule as specified. It demonstrates that the schema is
  mechanically producible from real revision history; its `valid_until` values should not
  be used as ground truth, since the rule behind them agrees with human judgment only 40%
  of the time.

## Decision

Agreement of 40% is below the 80% bar, so W2 is cut and no Wikipedia loader was built.
The evaluation uses W1 only. The report's Discussion states that all staleness results
therefore come from a self-authored generator, and cites this spike as the measurement
behind that limitation: a Wikipedia-derived alternative was attempted and found to need a
more accurate invalidation rule than this one, rather than being skipped untested.
