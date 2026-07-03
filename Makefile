# Convenience targets. The library itself has no build step; these just wrap
# the common developer actions.

PYTHON ?= .virtualenv/bin/python

.PHONY: help test lint build docker-build clean

help:
	@echo "make test          run the hardware-free test suite"
	@echo "make build         build sdist + wheel locally into ./dist"
	@echo "make docker-build  build sdist + wheel in Docker into ./dist (isolated)"
	@echo "make clean         remove build artifacts and caches"

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m build --sdist --wheel --outdir dist

docker-build:
	./scripts/docker-build.sh

clean:
	rm -rf dist build *.egg-info .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
