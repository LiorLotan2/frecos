# FreCoS

FreCoS (Freshness- and Cost-aware Serving) extends GPTCache with a learned per-cluster
staleness model, used both as a validity gate on the serve path and as a decay term in
eviction. It is a course project built on top of a pinned GPTCache fork; see
`report/report.pdf` for the full write-up (design, experiments, results).

## Repository layout

- `vendor/gptcache/` - pinned GPTCache source, read-only after import.
- `gptcache_ext/` - the extension package (pipeline, staleness model, eviction).
- `workloads/` - trace generators (synthetic and Wikipedia-derived).
- `benchmarks/` - the harness, metrics, and experiment runners.
- `tests/` - unit tests, the reference oracle, and the invariant suite.
- `docs/` - supporting write-ups (baseline source map, Wikipedia feasibility spike).
- `report/` - the final report (LaTeX source and compiled PDF).

## GPTCache baseline

Vendored from https://github.com/zilliztech/GPTCache at commit
`bae7ffeef774e762d9d4e60fce70be00011188a6` (tag `0.1.44`). See `vendor/gptcache/PIN.md`
for what was trimmed and why. Every line reference to baseline behavior used in the
design doc and report is re-verified against this commit in
`docs/baseline-source-map.md`.

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

## Running tests

```
make test
```

`make bench-smoke` is currently a stub; the benchmark harness lands with agent card A7.

## Docker

```
docker build -t frecos .
docker run frecos
```

This runs `make test` inside the container.

<!-- BENCHMARK:A7 -->
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
<!-- /BENCHMARK:A7 -->
