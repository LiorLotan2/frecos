"""Deterministic synthetic workload generator (W1) for FreCoS.

Emits a frozen trace schema. Every query stream is one of four kinds:

- canonical: the first occurrence of a ground-truth answer in a cluster. Establishes the
  answer_id, half_life, and regen_cost that later paraphrases and repeats reference.
- paraphrase: a reworded near-duplicate of a canonical query, same answer_id, distinct
  text. Stresses hit rate and false-hit rate.
- longtail: a unique query that never repeats, own answer_id, paraphrase_of null.
  Stresses admission and per-query overhead.
- repeat: the same canonical query asked again later, same answer_id. At least one repeat
  per repeating answer_id is placed strictly after that answer's valid_until, since
  without a timestamp crossing the boundary the staleness gate has nothing to reject.

All randomness goes through one numpy Generator seeded from the seed argument, drawn in a
fixed call order, so the same seed always reproduces the same trace byte for byte.
"""
import argparse
import json
import math

import numpy as np

BASE_TIME = 1_700_000_000.0

PARAPHRASE_PREFIXES = [
    "",
    "Could you tell me ",
    "I'm wondering, ",
    "Quick question, ",
    "Just to check, ",
    "Do you happen to know ",
]

PARAPHRASE_SUFFIXES = [
    "",
    " Thanks.",
    " Please explain.",
    " If you know.",
]

LONGTAIL_TOPICS = [
    "gadget", "recipe", "movie", "algorithm", "planet", "language", "sport", "artist",
    "country", "invention", "animal", "chemical", "instrument", "disease", "battle",
]

# One distinct real-world subject per cluster_id (51 entries, cycled via modulo for
# n_clusters > 51), so a sentence embedder has an actual semantic signal to separate
# clusters on. The prior template ("topic {cluster_id}-{answer_id}") differed across
# clusters only in a number, which a general-purpose embedder cannot use to recover
# cluster identity (see CHANGES.md / the remediation review this fixes).
CLUSTER_TOPICS = [
    "the Amazon rainforest", "the Roman Empire", "quantum computing",
    "the 1969 moon landing", "Bitcoin", "the human immune system",
    "Renaissance art", "the Great Barrier Reef", "machine learning",
    "the French Revolution", "black holes", "the printing press",
    "coral reefs", "the Cold War", "solar panels", "the Ottoman Empire",
    "genetic engineering", "the Industrial Revolution", "volcanic eruptions",
    "the 1929 stock market crash", "Antarctic ice sheets", "the Berlin Wall",
    "nuclear fusion", "the Silk Road", "electric vehicles",
    "the Byzantine Empire", "deep-sea ecosystems", "the Gutenberg Bible",
    "artificial intelligence ethics", "the Panama Canal", "medieval castles",
    "the Human Genome Project", "the Suez Canal crisis", "dinosaur extinction",
    "the Manhattan Project", "coral bleaching", "the fall of Constantinople",
    "vaccine development", "the Wright brothers' first flight",
    "the Great Wall of China", "cryptocurrency regulation",
    "the Chernobyl disaster", "space tourism", "the invention of the telephone",
    "urban heat islands", "the Maya civilization", "quantum entanglement",
    "the transatlantic slave trade", "renewable energy storage",
    "the assassination of Archduke Franz Ferdinand", "gene therapy",
]

# Two independent axes combined by (answer_id % len(ANSWER_ASPECTS), answer_id //
# len(ANSWER_ASPECTS) % len(ANSWER_QUALIFIERS)) give 25*30=750 distinct phrases per
# cluster -- comfortably above the largest per-cluster canonical-answer count this
# generator produces (~420 at the historical 12000-query/10-cluster scale) -- so two
# different answer_ids in the same cluster never collide on identical text. Colliding
# text would make two distinct answers textually indistinguishable, which is a
# duplicate-key artifact, not a modeling result, and would inflate false_hit_rate for
# a reason unrelated to embedder or clustering quality.
ANSWER_ASPECTS = [
    "population trends", "funding history", "environmental impact",
    "recent controversies", "economic significance", "technological advances",
    "cultural influence", "current research directions", "policy debates",
    "historical timeline", "public perception", "safety regulations",
    "market impact", "scientific consensus", "international cooperation efforts",
    "long-term projections", "notable case studies", "key milestones",
    "expert opinions", "ongoing challenges", "regulatory oversight",
    "media coverage", "academic debate", "public investment", "risk assessments",
]

ANSWER_QUALIFIERS = [
    "this year", "over the last decade", "in the latest report",
    "according to recent studies", "in the current climate", "this quarter",
    "based on new evidence", "following recent developments",
    "in light of new data", "as of the most recent review",
    "under current policy", "given recent events", "in the near term",
    "according to independent analysts", "in the wake of new findings",
    "under the latest guidelines", "as reported this month",
    "in ongoing discussions", "per the newest assessment",
    "in the most recent cycle", "following the latest hearing",
    "under revised estimates", "in the context of current trends",
    "as of the last audit", "given the latest projections",
    "in recent commentary", "under the updated framework",
    "as of the most recent survey", "in light of ongoing debate",
    "per the latest briefing",
]


def cluster_params(n_clusters, rng):
    """Per-cluster ground-truth distributions for half-life (seconds) and regen_cost (USD).

    half_life ~ Exponential(scale=half_life_scale[c]); this is the same exponential
    survival model the staleness fitter assumes, so oracle mode can recover it exactly.
    regen_cost and size_bytes are independent per-cluster lognormals, ranges chosen to be
    plausible for hosted LLM inference (see docs/w1-calibration.md for the honesty caveat).
    """
    half_life_scale = rng.uniform(3600.0 * 6, 3600.0 * 24 * 14, size=n_clusters)
    regen_cost_mu = rng.uniform(np.log(0.0005), np.log(0.01), size=n_clusters)
    regen_cost_sigma = rng.uniform(0.3, 0.6, size=n_clusters)
    size_bytes_mu = rng.uniform(np.log(200), np.log(3000), size=n_clusters)
    size_bytes_sigma = rng.uniform(0.2, 0.5, size=n_clusters)
    return {
        "half_life_scale": half_life_scale,
        "regen_cost_mu": regen_cost_mu,
        "regen_cost_sigma": regen_cost_sigma,
        "size_bytes_mu": size_bytes_mu,
        "size_bytes_sigma": size_bytes_sigma,
    }


def paraphrase_text(canonical_text, rng):
    # the empty prefix and empty suffix combination must never both be chosen, otherwise
    # the paraphrase is byte-identical to its canonical query, which defeats the point of
    # a "distinct text, same answer" stream.
    prefix_idx = rng.integers(len(PARAPHRASE_PREFIXES))
    if prefix_idx == 0:
        suffix_idx = rng.integers(1, len(PARAPHRASE_SUFFIXES))
    else:
        suffix_idx = rng.integers(len(PARAPHRASE_SUFFIXES))
    prefix = PARAPHRASE_PREFIXES[prefix_idx]
    suffix = PARAPHRASE_SUFFIXES[suffix_idx]
    body = canonical_text[0].lower() + canonical_text[1:] if prefix else canonical_text
    return f"{prefix}{body}{suffix}"


def longtail_text(index, rng):
    topic = LONGTAIL_TOPICS[rng.integers(len(LONGTAIL_TOPICS))]
    detail = rng.integers(0, 10_000_000)
    return f"What is notable about {topic} number {index}-{detail}?"


def zipf_pick(n_items, zipf_skew, rng):
    ranks = np.arange(1, n_items + 1, dtype=float)
    weights = ranks ** (-zipf_skew)
    weights /= weights.sum()
    return rng.choice(n_items, p=weights)


MIXTURE_FAST_FRACTION_OF_MEAN = 0.2
MIXTURE_SLOW_FRACTION_OF_MEAN = 1.8


def draw_half_life(scale, rng, shape=1.0, mode="exponential"):
    """Exponential (mode="exponential", the fitter's own assumed model) by default.

    mode="weibull" draws from a Weibull with the given shape instead, same mean as the
    exponential with that scale. A Weibull with shape > 1 has a *lower* coefficient of
    variation than the exponential it replaces (shape=2 roughly halves it), so this
    misspecification makes the workload's staleness easier to predict, not harder, even
    though the fitter's exponential assumption is technically wrong. Kept for reference.

    mode="mixture" draws from a 50/50 mixture of two exponentials, one with a fifth of
    the mean scale and one with 1.8 times it, same overall mean as the plain exponential
    with that scale. This is the adversarial case: a single exponential rate fit by
    maximum likelihood is systematically biased for both the fast and the slow
    subpopulation it is trying to average over, unlike the Weibull case above.
    """
    if mode == "mixture":
        fast_scale = scale * MIXTURE_FAST_FRACTION_OF_MEAN
        slow_scale = scale * MIXTURE_SLOW_FRACTION_OF_MEAN
        chosen_scale = fast_scale if rng.random() < 0.5 else slow_scale
        return float(rng.exponential(scale=chosen_scale))
    if shape == 1.0:
        return float(rng.exponential(scale=scale))
    weibull_scale = scale / math.gamma(1.0 + 1.0 / shape)
    return float(weibull_scale * rng.weibull(shape))


def draw_cost_and_size(params, cluster_id, rng):
    regen_cost = float(rng.lognormal(
        params["regen_cost_mu"][cluster_id], params["regen_cost_sigma"][cluster_id]
    ))
    size_bytes = int(rng.lognormal(
        params["size_bytes_mu"][cluster_id], params["size_bytes_sigma"][cluster_id]
    ))
    return regen_cost, max(size_bytes, 1)


def _force_staleness_boundary_crossings(rows, params, rng):
    """For every answer_id that repeats, guarantee at least one later row's t lands past
    the earliest row's valid_until.

    Paraphrases and time-shifted repeats both reuse an existing answer_id, so this has to
    run once over the whole trace after every stream has contributed its rows, not inside
    a single stream's loop, otherwise a paraphrase-only repeat of an answer_id never gets
    forced and the staleness gate is left with nothing to reject for it.
    """
    by_answer = {}
    for row in rows:
        by_answer.setdefault(row["answer_id"], []).append(row)

    for answer_id, group in by_answer.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: r["t"])
        earliest = group[0]
        if any(r["t"] > earliest["valid_until"] for r in group[1:]):
            continue
        cluster_id = earliest["cluster_id"]
        half_life_scale = params["half_life_scale"][cluster_id]
        latest = group[-1]
        gap = float(rng.exponential(scale=half_life_scale * 0.5))
        latest["t"] = earliest["valid_until"] + gap + 1.0
        latest["valid_until"] = latest["t"] + float(rng.exponential(scale=half_life_scale))


def generate_trace(
    n_tenants, n_clusters, n_queries, seed, zipf_skew=1.3,
    paraphrase_frac=0.25, longtail_frac=0.20, repeat_frac=0.20,
    base_mean_gap_seconds=3600.0, half_life_shape=1.0, half_life_mode="exponential",
):
    if n_clusters < 1 or n_queries < 1 or n_tenants < 1:
        raise ValueError("n_clusters, n_queries, n_tenants must be positive")
    canonical_frac = 1.0 - paraphrase_frac - longtail_frac - repeat_frac
    if canonical_frac <= 0:
        raise ValueError("paraphrase_frac + longtail_frac + repeat_frac must be < 1")

    rng = np.random.default_rng(seed)
    params = cluster_params(n_clusters, rng)

    n_canonical = max(n_clusters, int(round(n_queries * canonical_frac)))
    n_paraphrase = int(round(n_queries * paraphrase_frac))
    n_longtail = int(round(n_queries * longtail_frac))
    n_repeat = n_queries - n_canonical - n_paraphrase - n_longtail
    if n_repeat < 0:
        n_repeat = 0

    rows = []
    next_query_id = 0
    next_answer_id = 0

    # aggregate arrival rate scales with n_tenants: n independent Poisson streams merge
    # into one Poisson stream with n times the rate, so more tenants means shorter gaps.
    mean_gap = base_mean_gap_seconds / n_tenants
    canonical_gaps = rng.exponential(scale=mean_gap, size=n_canonical)
    canonical_times = BASE_TIME + np.cumsum(canonical_gaps)

    clusters_canonicals = [[] for _ in range(n_clusters)]

    for i in range(n_canonical):
        cluster_id = i % n_clusters
        # position of this answer among its own cluster's canonicals (0, 1, 2, ...),
        # not the global answer_id, since answer_id increments across every cluster
        # and its stride mod n_clusters can alias back onto the same aspect index far
        # sooner than the vocabulary actually repeats.
        local_index = i // n_clusters
        answer_id = next_answer_id
        next_answer_id += 1
        t = float(canonical_times[i])
        half_life = draw_half_life(
            params["half_life_scale"][cluster_id], rng, shape=half_life_shape, mode=half_life_mode
        )
        regen_cost, size_bytes = draw_cost_and_size(params, cluster_id, rng)
        query_id = next_query_id
        next_query_id += 1
        aspect = ANSWER_ASPECTS[local_index % len(ANSWER_ASPECTS)]
        qualifier = ANSWER_QUALIFIERS[
            (local_index // len(ANSWER_ASPECTS)) % len(ANSWER_QUALIFIERS)
        ]
        row = {
            "t": t,
            "query_id": query_id,
            "text": (
                f"What is the current status of {aspect} "
                f"for {CLUSTER_TOPICS[cluster_id % len(CLUSTER_TOPICS)]}, {qualifier}?"
            ),
            "cluster_id": cluster_id,
            "answer_id": answer_id,
            "valid_until": t + half_life,
            "regen_cost": regen_cost,
            "size_bytes": size_bytes,
            "paraphrase_of": None,
            "split": None,
        }
        rows.append(row)
        clusters_canonicals[cluster_id].append(row)

    nonempty_clusters = [c for c in range(n_clusters) if clusters_canonicals[c]]

    def pick_canonical(rng):
        cluster_id = nonempty_clusters[rng.integers(len(nonempty_clusters))]
        pool = clusters_canonicals[cluster_id]
        idx = zipf_pick(len(pool), zipf_skew, rng)
        return pool[idx]

    for _ in range(n_paraphrase):
        canonical = pick_canonical(rng)
        cluster_id = canonical["cluster_id"]
        t = canonical["t"] + float(rng.exponential(scale=mean_gap))
        half_life = draw_half_life(
            params["half_life_scale"][cluster_id], rng, shape=half_life_shape, mode=half_life_mode
        )
        regen_cost, size_bytes = draw_cost_and_size(params, cluster_id, rng)
        query_id = next_query_id
        next_query_id += 1
        rows.append({
            "t": t,
            "query_id": query_id,
            "text": paraphrase_text(canonical["text"], rng),
            "cluster_id": cluster_id,
            "answer_id": canonical["answer_id"],
            "valid_until": t + half_life,
            "regen_cost": regen_cost,
            "size_bytes": size_bytes,
            "paraphrase_of": canonical["query_id"],
            "split": None,
        })

    for i in range(n_longtail):
        cluster_id = nonempty_clusters[rng.integers(len(nonempty_clusters))]
        span = canonical_gaps.sum() * 1.3 if n_canonical else mean_gap
        t = BASE_TIME + float(rng.uniform(0, span))
        half_life = draw_half_life(
            params["half_life_scale"][cluster_id], rng, shape=half_life_shape, mode=half_life_mode
        )
        regen_cost, size_bytes = draw_cost_and_size(params, cluster_id, rng)
        query_id = next_query_id
        next_query_id += 1
        answer_id = next_answer_id
        next_answer_id += 1
        rows.append({
            "t": t,
            "query_id": query_id,
            "text": longtail_text(i, rng),
            "cluster_id": cluster_id,
            "answer_id": answer_id,
            "valid_until": t + half_life,
            "regen_cost": regen_cost,
            "size_bytes": size_bytes,
            "paraphrase_of": None,
            "split": None,
        })

    for _ in range(n_repeat):
        canonical = pick_canonical(rng)
        cluster_id = canonical["cluster_id"]
        answer_id = canonical["answer_id"]
        half_life_scale = params["half_life_scale"][cluster_id]
        t = canonical["t"] + float(rng.exponential(scale=mean_gap))
        half_life = draw_half_life(half_life_scale, rng, shape=half_life_shape, mode=half_life_mode)
        regen_cost, size_bytes = draw_cost_and_size(params, cluster_id, rng)
        query_id = next_query_id
        next_query_id += 1
        rows.append({
            "t": t,
            "query_id": query_id,
            "text": canonical["text"],
            "cluster_id": cluster_id,
            "answer_id": answer_id,
            "valid_until": t + half_life,
            "regen_cost": regen_cost,
            "size_bytes": size_bytes,
            "paraphrase_of": None,
            "split": None,
        })

    _force_staleness_boundary_crossings(rows, params, rng)

    rows.sort(key=lambda r: (r["t"], r["query_id"]))

    calib_count = int(round(len(rows) * 0.3))
    for i, row in enumerate(rows):
        row["split"] = "calib" if i < calib_count else "eval"

    return rows


def write_jsonl(rows, path):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Generate the W1 synthetic workload trace.")
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-tenants", type=int, default=5)
    parser.add_argument("--n-clusters", type=int, default=10)
    parser.add_argument("--n-queries", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--zipf-skew", type=float, default=1.3)
    parser.add_argument("--paraphrase-frac", type=float, default=0.25)
    parser.add_argument("--longtail-frac", type=float, default=0.20)
    parser.add_argument("--repeat-frac", type=float, default=0.20)
    args = parser.parse_args()

    rows = generate_trace(
        n_tenants=args.n_tenants,
        n_clusters=args.n_clusters,
        n_queries=args.n_queries,
        seed=args.seed,
        zipf_skew=args.zipf_skew,
        paraphrase_frac=args.paraphrase_frac,
        longtail_frac=args.longtail_frac,
        repeat_frac=args.repeat_frac,
    )
    write_jsonl(rows, args.out)


if __name__ == "__main__":
    main()
