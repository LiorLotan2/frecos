"""Fetch revision history for the 30 spike pages from the Wikipedia API and cache
the answer sentence extracted from each revision.

Run once. Writes one JSON file per question under revisions_cache/, each a list of
{revid, timestamp, sentence} so the rest of the spike (labeling, trace building)
runs offline against a fixed snapshot. Only the extracted sentence is kept, not
the full wikitext of every revision (~150KB each): the sentence is all downstream
steps need, and keeping full wikitext for 30 pages x 60 revisions makes the cache
too large to commit for a feasibility spike.
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path

from wikitext import find_answer_sentence

SPIKE_DIR = Path(__file__).parent
CACHE_DIR = SPIKE_DIR / "revisions_cache"
API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "frecos-course-project/1.0 (spike; contact: student@example.edu)"
REVISIONS_PER_PAGE = 60


def fetch_revisions(title, limit=REVISIONS_PER_PAGE):
    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "titles": title,
        "prop": "revisions",
        "rvlimit": str(limit),
        "rvprop": "timestamp|ids|content",
        "rvslots": "main",
    }
    url = API_URL + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    page = data["query"]["pages"][0]
    if "revisions" not in page:
        return []
    revisions = []
    for rev in page["revisions"]:
        content = rev["slots"]["main"].get("content")
        if content is None:
            continue  # revision-deleted content, rare, skip
        revisions.append({
            "revid": rev["revid"],
            "timestamp": rev["timestamp"],
            "content": content,
        })
    revisions.reverse()  # oldest first
    return revisions


def main():
    CACHE_DIR.mkdir(exist_ok=True)
    questions = json.loads((SPIKE_DIR / "questions.json").read_text())
    for question in questions:
        title = question["title"]
        out_path = CACHE_DIR / f"{title}.json"
        if out_path.exists():
            continue
        print(f"fetching {title}")
        revisions = fetch_revisions(title)
        extracted = [{
            "revid": r["revid"],
            "timestamp": r["timestamp"],
            "sentence": find_answer_sentence(r["content"], question["answer"]),
        } for r in revisions]
        out_path.write_text(json.dumps(extracted, indent=1))
        time.sleep(0.5)


if __name__ == "__main__":
    main()
