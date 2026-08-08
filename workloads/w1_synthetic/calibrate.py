"""Calibration check for the W1 generator's regen_cost and half_life distributions.

The intended references are the Azure LLM Inference Trace for regen_cost and
update-frequency patterns in a public news/catalog corpus for half_life. Neither dataset is
reachable from this sandboxed environment (no network access, no bundled copy of either
corpus). Rather than claim a fit this project never performed, this script generates a
literature-informed synthetic reference distribution for each quantity and plots the
generator's own output against it as a plausibility check, not a real external fit.

regen_cost reference: a lognormal built from publicly reported per-request cost ranges for
hosted LLM completions (roughly $0.0005 to $0.02 per request for short-to-medium answers
at 2024-2025 API pricing), not a fit to the Azure trace itself.

half_life reference: an exponential built from commonly cited content-refresh cadences
(breaking news measured in hours, general reference or catalog content on the order of
days to a couple of weeks), not a fit to any specific news or catalog corpus.
"""
import argparse
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from workloads.w1_synthetic.generator import generate_trace  # noqa: E402

REGEN_COST_REFERENCE_MU = np.log(0.003)
REGEN_COST_REFERENCE_SIGMA = 0.6

HALF_LIFE_REFERENCE_SCALE_SECONDS = 3600.0 * 24 * 3


def collect_regen_costs(rows):
    return np.array([row["regen_cost"] for row in rows])


def collect_half_lives(rows):
    return np.array([
        row["valid_until"] - row["t"] for row in rows if row["valid_until"] < float("inf")
    ])


def plot_overlay(synthetic_values, reference_values, xlabel, title, out_path, xscale="linear"):
    fig, ax = plt.subplots(figsize=(6, 4))
    bins = 40
    ax.hist(
        synthetic_values, bins=bins, density=True, alpha=0.5,
        label="W1 synthetic", color="tab:blue",
    )
    ax.hist(
        reference_values, bins=bins, density=True, alpha=0.5,
        label="literature-informed target range", color="tab:orange",
    )
    ax.set_xlabel(xlabel)
    ax.set_ylabel("density")
    ax.set_title(title)
    if xscale == "log":
        ax.set_xscale("log")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(
        description="Plot W1 distributions against literature-informed reference targets."
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-queries", type=int, default=20000)
    parser.add_argument("--out-dir", default="docs/figures")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    rows = generate_trace(n_tenants=5, n_clusters=10, n_queries=args.n_queries, seed=args.seed)

    regen_costs = collect_regen_costs(rows)
    rng = np.random.default_rng(args.seed + 1)
    reference_costs = rng.lognormal(
        REGEN_COST_REFERENCE_MU, REGEN_COST_REFERENCE_SIGMA, size=len(regen_costs)
    )
    plot_overlay(
        regen_costs, reference_costs,
        xlabel="regen_cost (USD)",
        title="W1 regen_cost vs literature-informed proxy",
        out_path=os.path.join(args.out_dir, "regen_cost_overlay.png"),
        xscale="log",
    )

    half_lives = collect_half_lives(rows)
    reference_half_lives = rng.exponential(HALF_LIFE_REFERENCE_SCALE_SECONDS, size=len(half_lives))
    plot_overlay(
        half_lives / 3600.0, reference_half_lives / 3600.0,
        xlabel="half_life (hours)",
        title="W1 half_life vs literature-informed proxy",
        out_path=os.path.join(args.out_dir, "half_life_overlay.png"),
        xscale="log",
    )

    print(
        f"regen_cost: synthetic median={np.median(regen_costs):.5f} "
        f"reference median={np.median(reference_costs):.5f}"
    )
    print(
        f"half_life hours: synthetic median={np.median(half_lives)/3600:.2f} "
        f"reference median={np.median(reference_half_lives)/3600:.2f}"
    )


if __name__ == "__main__":
    main()
