PYTHON ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python))

.PHONY: up down train test lint clean help

help:
	@echo "Targets:"
	@echo "  make up          - Build and deploy the entire system from fresh clone"
	@echo "  make down        - Tear down the k3d cluster"
	@echo "  make train       - Train Pythia-70M student model (use SUBSET=50 for quick test)"
	@echo "  make test        - Run unit tests with pytest"
	@echo "  make lint        - Run linting with ruff"

up:
	$(PYTHON) tools/setup_cluster.py

down:
	k3d cluster delete cloud-assignment

train:
	$(PYTHON) training/train.py $(if $(SUBSET),--subset $(SUBSET),)

test:
	$(PYTHON) -m pytest -v tests/test_unit.py

lint:
	ruff check .
