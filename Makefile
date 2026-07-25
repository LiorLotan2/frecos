PYTHON ?= python3
PYTEST := PYTHONPATH=vendor/gptcache:. $(PYTHON) -m pytest

.PHONY: install test bench-smoke verify

install:
	$(PYTHON) -m pip install -r vendor/gptcache/requirements.txt
	$(PYTHON) -m pip install pytest pytest-benchmark flake8 psutil

test:
	$(PYTEST)

bench-smoke:
	@echo "bench-smoke: harness not built yet (see A7 in docs/implementation-plan.md)"

verify: test bench-smoke
