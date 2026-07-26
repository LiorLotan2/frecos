# FreCoS

FreCoS (Freshness- and Cost-aware Serving) extends GPTCache with a learned per-cluster
staleness model, used both as a validity gate on the serve path and as a decay term in
eviction. It is a course project built on top of a pinned GPTCache fork; see
`report/report.pdf` for the full write-up (design, experiments, results).

## Repository layout

- `vendor/gptcache/` - pinned GPTCache source, read-only after import.
- `gptcache_ext/` - the extension package (pipeline, staleness model, eviction).
- `workloads/` - the W1 synthetic trace generator; `w2_wikipedia/spike/` holds a
  feasibility spike that was not carried forward (see "Reproducing the report" below).
- `benchmarks/` - the harness, metrics, and experiment runners.
- `tests/` - unit tests, the reference oracle, and the invariant suite.
- `docs/` - supporting write-ups (baseline source map, Wikipedia feasibility spike).
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

With conda:

```
conda env create -f environment.yml
conda activate frecos
```

Or with a plain venv:

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

**Runtimes below are stale** (measured before the embedder-based clustering and
semantic index were wired in) and are being remeasured against the current code; see
`CHANGES.md` for the up-to-date numbers once that rerun completes. Every runner now
also embeds each distinct query text once via the vendored ONNX model (cached to disk
under `.embedding_cache/`, gitignored, keyed by text hash), which dominates first-run
wall-clock; reruns against a warm cache are much faster.

| Command | Output CSV | Report table/figure |
|---|---|---|
| `make exp-brackets` | `results/brackets/results.csv` | Table `tab:brackets`, `tab:brackets-counts`, Figure `fig:brackets` |
| `make exp-ablation` | `results/ablation/results.csv` | Table `tab:ablation`, `tab:latency`, Figure `fig:ablation` |
| `make exp-brackets-calibration-sweep` | `results/brackets/calibration_sweep/results.csv` | Figure `fig:brackets` (sparser-calibration series) |
| `make exp-brackets-misspecified` | `results/brackets/misspecified/results.csv` | Discussion §5.1 (Weibull attempt, not tabled) |
| `make exp-brackets-mixture` | `results/brackets/mixture/results.csv` | Table `tab:misspec` |
| `make exp-sweeps` | `results/sweeps/{cache_size,cluster_k,ttl_confidence}/results.csv` | Table `tab:ttl`, Figures `fig:cachesize`, `fig:tradeoff` |
| `make exp-cost-aware-eviction` | `results/cost_aware_eviction/results.csv` | Discussion §5.3 (gate-off cost-aware eviction test) |

`make experiments` runs all seven sequentially. (An earlier eighth runner,
`benchmarks/runners/size_term_isolation.py`, was removed after its own finding -- the
committed `results/ablation/size_term_isolation/` is no longer regenerable, since
FreCoS's eviction value function no longer has a size-normalization term to isolate;
see `gptcache_ext/eviction/frecos.py`'s module docstring and `CHANGES.md`.)

`make figures` regenerates all four PNGs under `analysis/figures/` plus
`analysis/figures/supplementary.csv` from the committed CSVs above (~2s; no figure is
hand-edited). `make report` compiles `report/report.tex` to `report/report.pdf`
(requires a local `pdflatex`, not installed in this environment by `make install`).

`make experiments && make figures && make report`, run in that order from a clean
clone, reproduces every artifact this report cites.

Table in `report/report.tex` Appendix B (`tab:appendix`) maps every artifact used in
the report to its path in this repository.

## License

MIT, see `LICENSE`. Vendored GPTCache code under `vendor/gptcache/` retains its own
MIT license (`vendor/gptcache/LICENSE`); see `vendor/gptcache/PIN.md` for provenance.
