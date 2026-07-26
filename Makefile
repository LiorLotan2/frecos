PYTHON ?= python3
RUNPY := PYTHONPATH=vendor/gptcache:. $(PYTHON)
PYTEST := $(RUNPY) -m pytest

.PHONY: install test bench-smoke experiment-smoke verify \
	experiments exp-brackets exp-ablation exp-brackets-calibration-sweep \
	exp-brackets-misspecified exp-brackets-mixture exp-size-term-isolation exp-sweeps \
	figures report

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTEST)

bench-smoke:
	$(PYTEST) tests/test_bench_smoke.py -q

experiment-smoke:
	$(RUNPY) -m benchmarks.experiment_smoke

verify: test bench-smoke

exp-brackets:
	$(RUNPY) -m benchmarks.runners.brackets

exp-ablation:
	$(RUNPY) -m benchmarks.runners.ablation

exp-brackets-calibration-sweep:
	$(RUNPY) -m benchmarks.runners.brackets_calibration_sweep

exp-brackets-misspecified:
	$(RUNPY) -m benchmarks.runners.brackets_misspecified

exp-brackets-mixture:
	$(RUNPY) -m benchmarks.runners.brackets_mixture

exp-size-term-isolation:
	$(RUNPY) -m benchmarks.runners.size_term_isolation

exp-sweeps:
	$(RUNPY) -m benchmarks.runners.sweeps

# Dependency order: brackets before its calibration/misspecification/mixture
# follow-ups, ablation before the size-term-isolation follow-up.
experiments: exp-brackets exp-ablation exp-brackets-calibration-sweep \
	exp-brackets-misspecified exp-brackets-mixture exp-size-term-isolation exp-sweeps

figures:
	PYTHONPATH=vendor/gptcache:.:analysis $(PYTHON) analysis/make_figures.py

report:
	cd report && pdflatex -interaction=nonstopmode report.tex && pdflatex -interaction=nonstopmode report.tex
