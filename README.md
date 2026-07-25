# FreCoS

FreCoS (Freshness- and Cost-aware Serving) extends GPTCache with a learned per-cluster
staleness model, used both as a validity gate on the serve path and as a decay term in
eviction. It is a course project built on top of a pinned GPTCache fork; see
`docs/frecos-design-v2.md` for the design and `docs/implementation-plan.md` for how the
work is broken up across agent cards.

## Repository layout

- `vendor/gptcache/` - pinned GPTCache source, read-only after import.
- `gptcache_ext/` - the extension package (pipeline, staleness model, eviction).
- `workloads/` - trace generators (synthetic and Wikipedia-derived).
- `benchmarks/` - the harness, metrics, and experiment runners.
- `tests/` - unit tests, the reference oracle, and the invariant suite.
- `docs/` - design spec, implementation plan, and supporting write-ups.

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
Benchmark instructions land here once the harness exists (agent card A7).
<!-- /BENCHMARK:A7 -->
