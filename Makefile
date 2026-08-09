PYTHON ?= python3
RUNPY := PYTHONPATH=vendor/gptcache:. $(PYTHON)
PYTEST := $(RUNPY) -m pytest

.PHONY: install test bench-smoke experiment-smoke verify \
	experiments exp-brackets exp-ablation exp-brackets-calibration-sweep \
	exp-brackets-misspecified exp-brackets-mixture exp-sweeps exp-cost-aware-eviction \
	figures multiple-comparisons report

install:
	@$(PYTHON) -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info < (3, 14) else 1)" \
		|| (echo "error: $(PYTHON) is $$($(PYTHON) --version 2>&1); this project requires Python 3.10 through 3.13 (numpy==2.2.6 publishes no wheels below 3.10, and onnxruntime==1.23.2 publishes none for 3.14+). Point PYTHON at an interpreter in that range, e.g. \`make install PYTHON=python3.13\`." && exit 1)
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

exp-sweeps:
	$(RUNPY) -m benchmarks.runners.sweeps

exp-cost-aware-eviction:
	$(RUNPY) -m benchmarks.runners.cost_aware_eviction

# Dependency order: brackets before its calibration/misspecification/mixture
# follow-ups.
experiments: exp-brackets exp-ablation exp-brackets-calibration-sweep \
	exp-brackets-misspecified exp-brackets-mixture exp-sweeps exp-cost-aware-eviction

figures:
	PYTHONPATH=vendor/gptcache:.:analysis $(PYTHON) analysis/make_figures.py

multiple-comparisons:
	PYTHONPATH=vendor/gptcache:.:analysis $(PYTHON) analysis/multiple_comparisons.py

report:
	cd report && tectonic report.tex
