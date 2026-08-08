"""Shared plotting and stats helpers for the A11 figures.

Bootstrap method mirrors the one already used in every results/*/summary.md:
percentile bootstrap, 10,000 resamples with replacement, seeded stdlib random
(seed 12345), median of each resample, 95% CI from the 2.5th/97.5th
percentiles. Reusing the same seed and method here means the CIs plotted
match the ones already reported in the summaries, rather than introducing a
second, slightly different set of numbers for the same data.
"""
import csv
import random
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = Path(__file__).resolve().parent / "figures"

BOOTSTRAP_SEED = 12345
BOOTSTRAP_RESAMPLES = 10000

# Figure source dimensions are chosen so that a figure rendered at its intended width in
# report/report.tex lands close to 1:1, which keeps its tick and axis labels near the
# report's own 10-11pt body size. A 7-inch-wide source scaled into a 3.9-inch slot shrinks
# 11pt type to under 5pt, which is what these two presets exist to avoid.
#   default: rendered at 0.62\textwidth (about 3.9in) -> fig1, fig2
#   small:   rendered at 0.48\textwidth (about 3.0in) in a minipage pair -> fig3, fig4
FIG_WIDTH = 4.2
FIG_HEIGHT = 2.7
FIG_WIDTH_SMALL = 3.3
FIG_HEIGHT_SMALL = 2.5
FIG_DPI = 150
FONT_SIZE = 11

plt.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.labelsize": FONT_SIZE,
    "axes.titlesize": FONT_SIZE + 1,
    "legend.fontsize": FONT_SIZE - 1,
    "xtick.labelsize": FONT_SIZE - 1,
    "ytick.labelsize": FONT_SIZE - 1,
})


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def bootstrap_median_ci(values):
    n = len(values)
    rng = random.Random(BOOTSTRAP_SEED)
    resample_medians = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        resample_medians.append(statistics.median(sample))
    resample_medians.sort()
    lo = resample_medians[int(0.025 * BOOTSTRAP_RESAMPLES)]
    hi = resample_medians[int(0.975 * BOOTSTRAP_RESAMPLES)]
    return statistics.median(values), lo, hi


def group_values(rows, key_fn, value_col):
    groups = {}
    for row in rows:
        groups.setdefault(key_fn(row), []).append(float(row[value_col]))
    return groups


def new_figure(small=False, height=None):
    width, default_height = (
        (FIG_WIDTH_SMALL, FIG_HEIGHT_SMALL) if small else (FIG_WIDTH, FIG_HEIGHT)
    )
    fig, ax = plt.subplots(figsize=(width, height or default_height))
    return fig, ax


def save_figure(fig, name):
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    out = FIGURES_DIR / name
    fig.savefig(out, dpi=FIG_DPI, bbox_inches="tight")
    plt.close(fig)
    return out
