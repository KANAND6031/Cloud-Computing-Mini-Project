PYTHON ?= $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,$(if $(wildcard .venv/bin/python),.venv/bin/python,python))

.PHONY: up down train test lint clean help

help:
	@echo "Targets:"
	@echo "  make up          - Create k3d cluster and deploy SeaweedFS"
	@echo "  make down        - Tear down the k3d cluster"
	@echo "  make train       - Train Pythia-70M student model (use SUBSET=50 for quick test)"
	@echo "  make test        - Run unit tests"
	@echo "  make lint        - Run linting with ruff"

up:
	k3d cluster create --config cluster/k3d.yaml || true
	kubectl apply -f deployment/seaweedfs.yaml

down:
	k3d cluster delete cloud-assignment

train:
	$(PYTHON) training/train.py $(if $(SUBSET),--subset $(SUBSET),)

test:
	$(PYTHON) -m pytest tests/

lint:
	ruff check .
