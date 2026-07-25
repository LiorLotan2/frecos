PYTHON ?= python3
PYTEST := PYTHONPATH=vendor/gptcache:. $(PYTHON) -m pytest

.PHONY: install test bench-smoke verify

install:
	$(PYTHON) -m pip install -r vendor/gptcache/requirements.txt
	$(PYTHON) -m pip install pytest pytest-benchmark flake8 psutil

test:
	$(PYTEST)

bench-smoke:
	$(PYTEST) tests/test_bench_smoke.py -q

verify: test bench-smoke
