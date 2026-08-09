# FreCoS

FreCoS (Freshness- and Cost-aware Serving) extends GPTCache with a learned per-cluster
staleness model, used both as a validity gate on the serve path and as a decay term in
eviction. It is a course project built on top of a pinned GPTCache fork; see
`report/report.pdf` for the full write-up (design, experiments, results).

## Quick start

Clone, install, and run the test suite:

```
git clone https://github.com/LiorLotan2/frecos.git
cd frecos
python3 -m venv .venv && source .venv/bin/activate
make install
make test
```

That needs a Python 3.10+ interpreter; see "Install" below if your default `python3` is
older. To skip local setup entirely and run the same checks in a container:

```
docker build -t frecos . && docker run frecos
```

To regenerate every number, table, and figure the report cites:

```
make experiments && make figures && make report
```

`make experiments` takes under 30 minutes with a warm embedding cache, `make figures` a
couple of seconds, and `make report` needs `tectonic` installed separately. What each
target produces, and the one committed result set that cannot be regenerated, are covered
under "Reproducing the report".

## What the experiments found

The validity gate works on the metric it targets. On the synthetic W1 workload it cuts
stale-hit-rate from 0.546 to 0.068, an 8.07-fold reduction with perfect separation across
5 seeds, and per-cluster learned rates beat a single pooled rate.

## The tradeoffs, and which of them are real

Turning the gate on moves four numbers the wrong way. Three are less damaging than they
first look; one is a genuine cost.

Hit rate falls from 0.894 to 0.336, but most of what disappears was wrong to begin with.
With the gate off, 0.9225 of served hits are false hits. Counted per scored query instead
of per served hit, useful hits move the other way: 0.0164 to 0.0265, a rise of 61.3%.

Mean latency rises from 15.64 to 95.55 ms and throughput falls from 63.96 to 10.47
queries/s, but neither is the gate's own cost. Measured extension overhead per decision is
1.04 ms with the gate off and 0.82 ms with it on, and the per-seed ranges overlap
(0.79 to 1.39 ms against 0.71 to 1.12 ms). The latency shift comes from the gate turning
hits into misses, and a miss in this harness pays a simulated placeholder latency far
larger than any cache-side decision.

Spend is the real cost: 4.317 against 0.669, a 6.45x rise, buying a 1.52x rise in cost
saved that is not significant at 5 seeds. Refusing a stale hit means paying to regenerate,
so saved-over-spent drops as the gate gets stricter, from 0.0480 at `ttl_confidence` 0.8
to 0.0351 at 0.99. This is the shape of the problem rather than an implementation defect.
`ttl_confidence` is the knob that trades the two sides against each other, and Table
`tab:ttl` in the report gives the measured frontier.

The fourth is the eviction decay term, and it does not work. In the one experiment where
the value function actually selects victims (a 25-entry budget), FreCoS is
indistinguishable from plain LFU on cost saved, and plain LRU beats it on both cost saved
and stale-hit-rate, because creation age tracks access recency on this trace. That is
reported as a negative result. The tempting repair, ranking victims by last access rather
than creation time, is LRU under another name; `tests/test_invariants.py` and
`tests/test_frecos.py` both fail any implementation that does it.

Every number above is reproducible from the committed CSVs under `results/`; see
"Reproducing the report" below.

## Repository layout

- `vendor/gptcache/` - pinned GPTCache source, read-only after import.
- `gptcache_ext/` - the extension package (pipeline, staleness model, eviction).
- `workloads/` - the W1 synthetic trace generator; `w2_wikipedia/spike/` holds a
  Wikipedia feasibility spike that was measured and cut (see `docs/w2-feasibility.md`).
- `benchmarks/` - the harness, metrics, and experiment runners.
- `tests/` - unit tests, the reference oracle, and the invariant suite.
- `docs/` - supporting write-ups: baseline choice (`baseline-justification.md`), the
  claim-by-claim baseline source map, related work, W1 calibration, and the W2
  feasibility spike.
- `report/` - the final report (LaTeX source and compiled PDF).
- `results/`, `analysis/` - committed experiment output and figure regeneration.

## GPTCache baseline

Vendored from https://github.com/zilliztech/GPTCache at commit
`bae7ffeef774e762d9d4e60fce70be00011188a6` (tag `0.1.44`). See `vendor/gptcache/PIN.md`
for what was trimmed and why. Every line reference to baseline behavior used in the
report is re-verified against this commit in `docs/baseline-source-map.md`.

Embedder: GPTCache's default ONNX model, `GPTCache/paraphrase-albert-onnx`
(tokenizer `GPTCache/paraphrase-albert-small-v2`), CPU-only. Not substituted, since
embeddings determine cluster assignment and similarity ranks used throughout.

## Install

Requires Python 3.10 or newer: `requirements.txt` pins `numpy==2.2.6`, whose wheels are
only published for CPython 3.10+. On a stock macOS `python3` (often 3.9), `pip install
-r requirements.txt` fails with a resolver error that does not name numpy as the cause;
`make install` checks this and fails fast with a clearer message instead.

With conda:

```
conda env create -f environment.yml
conda activate frecos
```

Or with a plain venv (use a `python3.10+` interpreter explicitly if your default
`python3` is older, e.g. `python3.13 -m venv .venv`):

```
python3 -m venv .venv
source .venv/bin/activate
make install
```

Both paths install the exact same pinned versions (`requirements.txt`); `make install`
runs `pip install -r requirements.txt` under the venv, and `environment.yml` pins
the identical versions for conda.

## Running tests

```
make test
```

## Docker

```
docker build -t frecos .
docker run frecos
```

This runs `make verify` (tests + the smoke benchmark) inside the container. To
reproduce the report's experiments or figures instead:

```
docker run frecos make experiments
docker run frecos make figures
```

## How to benchmark

`benchmarks/harness.py` replays a trace (JSONL) through `gptcache_ext.pipeline.decide()`
and produces one results-CSV row per run. No LLM is called: miss content and cost come
straight from the trace, and miss latency is a seeded placeholder distribution, not one
fit to a real trace. See the docstring at the top of `harness.py` for the full simulation
model and CSV schema.

The smoke benchmark (`benchmarks/smoke.py`) runs a small, fixed, deterministic 40-row
trace through the harness with LRU eviction and the gate disabled. Reproduce the
committed sample row with:

```
make bench-smoke
```

or directly:

```
PYTHONPATH=vendor/gptcache:. python -m benchmarks.smoke --csv /tmp/out.csv --json /tmp/out.json
```

This reproduces `benchmarks/samples/smoke_row.csv` / `smoke_row.json` exactly on every
count and rate column (`n_queries`, `n_hits`, `hit_rate`, `stale_hit_rate`, ...). The
latency, throughput, and resource columns are real wall-clock measurements and vary run
to run.

To benchmark your own trace and config, call `benchmarks.harness.run_harness(trace,
config, seed, gate, eviction_policy, staleness_table)` with objects satisfying the
`Gate`, `EvictionPolicy`, and `StalenessTable` protocols in `gptcache_ext/contracts.py`,
then `benchmarks.harness.write_csv_row(row, path)` to append it to a results CSV.

## Reproducing the report

Section 5's experiments are separate from the smoke benchmark above. Each experiment
is a runner module under `benchmarks/runners/`, a thin script over `harness.py` that
writes its results CSV under `results/`. `make experiments` runs all seven in dependency
order; each also has its own `make exp-*` target if you only want to rerun one.
`make experiment-smoke` exercises the same runner code path on a tiny trace in seconds,
which is what CI runs instead of the full set.

Each runner embeds every distinct query text once via the vendored ONNX model (cached to
disk under `.embedding_cache/`, gitignored, keyed by text hash), which dominates first-run
wall-clock. An experiment that reuses trace texts an earlier one already embedded is far
faster than a cold run, since it hits a warm cache. At the scale the report uses (3,000 queries, 5 seeds per
experiment), a full `make experiments` run with a warm embedding cache took under 30
minutes total on the machine recorded in each experiment's `env.json` (Apple M2 Pro,
macOS). That figure was not re-timed against a fully empty `.embedding_cache/`, so
treat it as a warm-cache lower bound rather than a cold-start estimate.

| Command | Output CSV | Report table/figure |
|---|---|---|
| `make exp-brackets` | `results/brackets/results.csv` | Table `tab:brackets`, Figure `fig:brackets` |
| `make exp-ablation` | `results/ablation/results.csv` | Table `tab:ablation`, `tab:latency`, Figure `fig:ablation` |
| `make exp-brackets-calibration-sweep` | `results/brackets/calibration_sweep/results.csv` | Figure `fig:brackets` (sparser-calibration series) |
| `make exp-brackets-misspecified` | `results/brackets/misspecified/results.csv` | Table `tab:misspec` |
| `make exp-brackets-mixture` | `results/brackets/mixture/results.csv` | Table `tab:misspec` |
| `make exp-sweeps` | `results/sweeps/{cache_size,cluster_k,ttl_confidence}/results.csv` | Table `tab:ttl`, Figures `fig:cachesize`, `fig:tradeoff` (cluster_k varies n_clusters, which changes the trace's canonical-query text and so cannot reuse most of the embedding cache the other experiments built) |
| `make exp-cost-aware-eviction` | `results/cost_aware_eviction/results.csv` | Table `tab:costaware` |

One committed result set,
`results/ablation/size_term_isolation/`, has no runner and cannot be regenerated: it was
recorded at a 12,000-query trace scale, on an earlier metric schema, by a `no_size` code
path that no longer exists. It is what established that FreCoS's value function needs no
size-normalization term, so the term was dropped and the toggle with it. See
`gptcache_ext/eviction/frecos.py`'s module docstring and
`results/ablation/size_term_isolation/summary.md`, which also notes that its
`cost_saved_usd` uses a different definition from every later run.

`make figures` regenerates all four PNGs under `analysis/figures/` plus
`analysis/figures/supplementary.csv` from the committed CSVs above (~2s; no figure is
hand-edited), using the exact `matplotlib` version pinned in `requirements.txt`.
A different version renders pixel-different PNGs even from identical data, which is
why the CI figures-consistency check installs from `requirements.txt` before
regenerating. That check is also platform-dependent: even with the pinned
`matplotlib` version, regenerating on macOS produces PNGs that differ byte-for-byte
from the Linux-rendered ones committed here (font rasterization differs by platform),
so `figures-consistency` is only verified to pass on the Linux CI runner, not on every
`make figures` invocation. `analysis/figures/supplementary.csv`, by contrast, does
reproduce byte-identically on macOS too, since it is plain-text numeric output with
no font rendering involved, making it the stronger reproducibility claim of the two
artifacts `make figures` produces.

The report's Figure 2 is not one of them. It is drawn in `report/report.tex` with pgfplots
from the medians in `results/ablation/results.csv`, so it needs no PNG and `analysis/figures/`
holds only the four matplotlib figures.

`make multiple-comparisons` prints the Holm-Bonferroni correction the report carries in
Appendix C: all twelve comparisons with raw and adjusted p, the two pre-registered primary
comparisons marked exempt, and the ten-member secondary family.

`make report` compiles `report/report.tex` to `report/report.pdf` via
`tectonic` (not `pdflatex`; installed separately, e.g. `brew install tectonic` or
see https://tectonic-typesetting.github.io/, not bundled by `make install`).

`make experiments && make figures && make report`, run in that order from a clean
clone, reproduces every artifact this report cites except
`results/ablation/size_term_isolation/`, noted above.

Appendix B of the report (`tab:appendix`) maps the code and data artifacts the report
cites to their paths in this repository.

## License

MIT, see `LICENSE`. Vendored GPTCache code under `vendor/gptcache/` retains its own
MIT license (`vendor/gptcache/LICENSE`); see `vendor/gptcache/PIN.md` for provenance.
