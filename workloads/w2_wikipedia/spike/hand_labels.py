"""20 hand-labeled (answer, revision-pair) cases and the agreement check against
the automatic rule in detect_invalidations.py.

Each case was pulled from candidate_pairs.json (rule said invalidating) or from
a random sample of same-sentence transitions (rule said non_invalidating), then
read by hand: does this edit actually change whether the SQuAD answer is still
correct, or is it a copyedit, spelling fix, terminology swap, capitalization
change, or infobox/template artifact that leaves the underlying fact intact?
"""

CASES = [
    {
        "title": "Southern_California", "answer": "SoCal",
        "sentence_before": "...generally comprises the southern portion of the U.S.",
        "sentence_after": "...comprises ten counties in the southern portion of the U.S.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Wording tightened (vague -> ten counties) but the queried fact, the SoCal abbreviation, is untouched.",
    },
    {
        "title": "1973_oil_crisis", "answer": "October 1973",
        "sentence_before": "[image caption]...In October 1973, the OAPEC announced...",
        "sentence_after": "[image caption]...In October 1973, the OAPEC announced...",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Only the image caption text preceding the sentence changed; the sentence extractor concatenated caption and prose. Extraction artifact, not a content edit.",
    },
    {
        "title": "Packet_switching", "answer": "Donald Davies",
        "sentence_before": "...Welsh computer scientist Donald Davies at the NPL...",
        "sentence_after": "...British computer scientist Donald Davies at the NPL...",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Nationality descriptor swapped; the answer (who did the work) is unaffected.",
    },
    {
        "title": "Black_Death", "answer": "Jani Beg",
        "sentence_before": "...siege of the Genoese trading port of Kaffa...",
        "sentence_after": "...siege of the Genoese trading port of Caffa...",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Spelling variant of the port name (Kaffa/Caffa); Jani Beg unchanged.",
    },
    {
        "title": "Civil_disobedience", "answer": "Civil disobedience",
        "sentence_before": "...active, and professed refusal...orders or commands...",
        "sentence_after": "...active and professed refusal...orders, or commands...",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Comma placement only.",
    },
    {
        "title": "Civil_disobedience", "answer": "Civil disobedience",
        "sentence_before": "Civil disobedience is the active and professed refusal...",
        "sentence_after": "By some definitions, civil disobedience has to be nonviolent to be called \"civil\".",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "A new sentence was inserted earlier in the paragraph; the first-match extractor now grabs it instead of the original definition, which is still present later in the same paragraph. Reordering artifact, not a genuine definition change.",
    },
    {
        "title": "Jacksonville,_Florida", "answer": "Duval",
        "sentence_before": "...county seat of Duval County, with which the city consolidated in 1968.",
        "sentence_after": "...county seat of Duval County, which the city consolidated in 1968.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Dropped the word 'with'; grammar only, same fact.",
    },
    {
        "title": "Jacksonville,_Florida", "answer": "Duval",
        "sentence_before": "...county seat of Duval County, with which the city consolidated in 1968.",
        "sentence_after": "[infobox key/value text]...Jacksonville...is the most populous city proper in the U.S.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "An infobox template was inserted above the sentence; the extractor's template stripping leaked infobox field text in its place. Extraction artifact.",
    },
    {
        "title": "Economic_inequality", "answer": "40%",
        "sentence_before": "OECD found out that 40%...compared with 33% some 20 years before.",
        "sentence_after": "OECD found that 40%...compared with 33% some 20 years earlier.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Copyedit ('found out' -> 'found', 'before' -> 'earlier'); same numbers.",
    },
    {
        "title": "Yuan_dynasty", "answer": "1271",
        "sentence_before": "[infobox] ...life_span = 1271-1368 AD | era = Post-classical history | status = Post-classical...",
        "sentence_after": "[infobox] ...life_span = 1271-1368 AD | era = Post-classical history | status = Sinicized nomadic empire...",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "The infobox 'status' field text changed; the life_span=1271 field the answer depends on did not.",
    },
    {
        "title": "Warsaw", "answer": "Vistula",
        "sentence_before": "The metropolis stands on the River Vistula in east-central Poland.",
        "sentence_after": "The metropolis stands on the river Vistula in east-central Poland.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Capitalization of 'river' only.",
    },
    {
        "title": "French_and_Indian_War", "answer": "1754–1763",
        "sentence_before": "...between Great Britain and France, along with their respective Native American allies.",
        "sentence_after": "...between Great Britain and France, along with their respective Indigenous allies.",
        "rule_verdict": "invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Terminology swap (Native American -> Indigenous); the date range answer is a separate clause, untouched.",
    },
    {
        "title": "Civil_disobedience", "answer": "Civil disobedience",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Amazon_rainforest", "answer": "Brazil",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Harvard_University", "answer": "1977",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Imperialism", "answer": "Latin",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Southern_California", "answer": "SoCal",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Steam_engine", "answer": "Rankine",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Intergovernmental_Panel_on_Climate_Change", "answer": "2001",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
    {
        "title": "Oxygen", "answer": "Robert Boyle",
        "sentence_before": "[unchanged]",
        "sentence_after": "[unchanged]",
        "rule_verdict": "non_invalidating",
        "human_verdict": "non_invalidating",
        "reason": "Sentence identical across the revision pair.",
    },
]


def agreement():
    matches = sum(1 for c in CASES if c["rule_verdict"] == c["human_verdict"])
    return matches, len(CASES)


if __name__ == "__main__":
    matches, total = agreement()
    assert total == 20, "expected exactly 20 hand-labeled cases"
    print(f"agreement: {matches}/{total} = {matches / total:.0%}")
