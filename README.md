# Cloud Computing (CS3081): Mini Project
## Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud

[![CI/CD Pipeline](https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/workflows/ci.yaml/badge.svg)](https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/workflows/ci.yaml)
[![Release](https://img.shields.io/github/v/release/KANAND6031/Cloud-Computing-Mini-Project)](https://github.com/KANAND6031/Cloud-Computing-Mini-Project/releases/tag/v1.0.0)

**GitHub Repository**: [https://github.com/KANAND6031/Cloud-Computing-Mini-Project](https://github.com/KANAND6031/Cloud-Computing-Mini-Project)

This repository contains the complete implementation, infrastructure configurations, training pipelines, and CI/CD automation for distilling a 3.8B parameter teacher model (`Phi-3.5-mini-instruct`) into a 70M parameter lightweight student model (`EleutherAI/pythia-70m`), containerizing it as a microservice, and deploying it with autoscaling and health probes to a local Kubernetes (`k3d`) cloud environment.

---

## 1. Quickstart Commands

The entire environment can be built, deployed, tested, and torn down using the provided [`Makefile`](Makefile):

### Build and Deploy the Whole System
From a fresh repository clone, deploy the complete cloud stack (k3d cluster, SeaweedFS object storage, S3 datasets/models, container build, Traefik ingress, and HPA deployment):
```bash
make up
```
*The service will be live and serving requests at `http://localhost:8080/parse`.*

### Run Unit Tests
Run the comprehensive unit test suite:
```bash
make test
```

### Run Code Quality Linting
Run Ruff code style and static analysis checks:
```bash
make lint
```

### Run Model Training (Knowledge Distillation)
Train the student model (`Pythia-70M`) on CPU:
```bash
# Full training on cleaned teacher dataset:
make train

# Rapid verification on a subset of 50 records:
make train SUBSET=50
```

### Tear Down Cluster
Delete the `cloud-assignment` k3d cluster and free all local container resources:
```bash
make down
```

---

## 2. API Endpoints

The inference service listens internally on port 8000 and is routed through the Traefik Ingress controller on port 8080:

### 1. `POST /parse`
Parses a natural language command into structured slot-intent JSON.
- **Request**:
  ```bash
  curl -X POST http://localhost:8080/parse \
       -H "Content-Type: application/json" \
       -d '{"text": "set an alarm for seven thirty am tomorrow"}'
  ```
- **Response** (`HTTP 200 OK`):
  ```json
  {"intent": "alarm_set", "date": "tomorrow", "time": "seven thirty am", "place": null}
  ```
- **Headers**:
  - `X-Model-Version`: Active model version (`v1` or `v2`)
  - `X-Served-By`: Pod name servicing the request

### 2. `GET /healthz`
Liveness probe endpoint returning `HTTP 200 OK` as long as the process is alive.

### 3. `GET /readyz`
Readiness probe endpoint returning `HTTP 503 Service Unavailable` while weights are downloading from S3, and `HTTP 200 OK` once the model is initialized.

---

## 3. Architecture Overview

```
                      Client Request (http://localhost:8080/parse)
                                          |
                                          v
                     +-----------------------------------------+
                     |    k3d Server Load Balancer (Port 8080) |
                     +-----------------------------------------+
                                          |
                                          v
                     +-----------------------------------------+
                     |        Traefik Ingress Controller       |
                     |         (inference-ingress, app)        |
                     +-----------------------------------------+
                                          |
                                          v
                     +-----------------------------------------+
                     |        ClusterIP Service (Port 8000)    |
                     +-----------------------------------------+
                               /                     \
                      (Round-Robin)               (Round-Robin)
                             /                         \
                            v                           v
              +--------------------------+  +--------------------------+
              | Pod Replica 1 (agent-0)  |  | Pod Replica 2 (agent-1)  |
              | CPU Limit: 1000m         |  | CPU Limit: 1000m         |
              | Mem Limit: 1Gi           |  | Mem Limit: 1Gi           |
              | Liveness: /healthz       |  | Liveness: /healthz       |
              | Readiness: /readyz       |  | Readiness: /readyz       |
              | preStop: sleep 5         |  | preStop: sleep 5         |
              +--------------------------+  +--------------------------+
                             ^                         ^
                             \------------+------------/
                                          |
                        +-----------------------------------+
                        | SeaweedFS S3 Object Storage       |
                        | (seaweedfs.data:8333, ns: data)   |
                        +-----------------------------------+
```

---

## 4. Repository Structure

```
.
├── cluster/
│   └── k3d.yaml                # k3d cluster config (1 server, 2 agents, serverlb 8080:80)
├── data/
│   ├── commands_pool.jsonl     # 3,000 raw input commands
│   ├── rate_card.json          # Hypothetical cloud pricing schedule
│   ├── schema.json             # Output JSON schema definition
│   └── validation.jsonl        # 100 labeled validation commands
├── deployment/
│   ├── app.yaml                # Namespace, Secret, Deployment, Service, and Ingress
│   ├── hpa.yaml                # HorizontalPodAutoscaler (min: 1, max: 2, 70% CPU)
│   ├── pipeline.yaml           # Multi-worker batch labelling jobs
│   └── seaweedfs.yaml          # S3-compatible SeaweedFS deployment with PVC
├── network/
│   ├── nacl.json               # Stateless NACL rules for public load balancer subnet
│   ├── packets_sample.jsonl    # NACL validation packets
│   └── subnets.md              # VLSM subnet allocation plan and derivations
├── prompts/
│   └── teacher_prompt.txt      # Prompt template for Phi-3.5 teacher labelling
├── report/
│   ├── report.pdf              # Compiled 8-page final project report
│   ├── task1.md to task7.md    # Detailed reports for Tasks 1 through 7
├── results/                    # Logs, scores, locust CSVs, and benchmark outputs
├── service/
│   ├── Dockerfile              # Minimal CPU-optimised container image (< 2 GB)
│   ├── app.py                  # FastAPI inference service with S3 loader & validation
│   └── requirements.txt        # Pinned dependencies
├── tests/
│   ├── test_unit.py            # Unit tests for cleaning, NACL, schema, and subnets
│   ├── test_cold_start.py      # Pod cold-start benchmarking script
│   ├── test_hpa.py             # Autoscaling verification script
│   ├── test_recovery.py        # Pod failure and self-healing test script
│   ├── test_rolling_update.py  # Zero-downtime rolling update & rollback script
│   └── run_task7_benchmark.py  # Locust load test and resource profiler runner
├── tools/
│   ├── locustfile.py           # Locust performance load testing script
│   ├── nacl_sim.py             # Stateless NACL network simulator
│   ├── score.py                # Model validation accuracy and validity scorer
│   └── setup_cluster.py        # Automated cluster bootstrap script (make up)
├── training/
│   ├── config.yaml             # Hyperparameters, random seed, and library versions
│   ├── train.py                # Causal LM sequence-level distillation fine-tuner
│   └── evaluate_ci.py          # Release asset evaluator for CI/CD quality gate
├── worker/
│   ├── clean.py                # Shard output cleaner and SHA-256 verifier
│   └── worker.py               # Distributed Ollama parallel labelling worker
├── AI_USE.md                   # AI tooling usage and verification disclosure
├── Makefile                    # System automation entrypoints
└── pyproject.toml              # Ruff and Pytest project configuration
```

---

## 5. Model Artifacts and GitHub Releases

Model weights are decoupled from the repository and published as release assets per project constraints:
- **Release Asset**: [`model.tar.gz`](https://github.com/KANAND6031/Cloud-Computing-Mini-Project/releases/tag/v1.0.0)
- **SHA-256 Checksum**: `dbc2a82188fff0df1ca8c8ab67cbfb9f5c79258e48036861978438260b80bae6` (recorded in `models/v1/model.sha256`)
