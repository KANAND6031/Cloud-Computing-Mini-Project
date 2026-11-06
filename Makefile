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
	python training/train.py $(if $(SUBSET),--subset $(SUBSET),)

test:
	pytest tests/

lint:
	ruff check .
