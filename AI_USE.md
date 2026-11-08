# AI Use and Verification Disclosure

In compliance with the project guidelines for **Cloud Computing (CS3081): Mini Project (Knowledge Distillation and Deployment on a Local Cloud)**, this document transparently describes:
1. Which AI tools and models were used;
2. The specific tasks and workflows they assisted with;
3. The verification methodologies and quality controls applied to check and validate all AI outputs.

---

## 1. AI Tools Used

| Tool / Model | Version / Provider | Role in Project |
| :--- | :--- | :--- |
| **Phi-3.5-mini-instruct** | `phi3.5:latest` (Ollama, 3.8B parameters) | Official teacher model for Sequence-Level Knowledge Distillation |
| **EleutherAI/pythia-70m** | Hugging Face Transformers (70M parameters) | Target student model trained via sequence-level distillation |
| **Antigravity AI Assistant** | Google DeepMind / Gemini Architecture | Pair programming assistant for scaffolding, scripts, and documentation |

---

## 2. Tasks and Usage Scope

### Task 1: Object Storage and Parallel Teacher Labelling
- **Usage**: 
  - Teacher prompt design in `prompts/teacher_prompt.txt` to enforce 4-key JSON generation (`intent`, `date`, `time`, `place`).
  - Automated generation of raw teacher responses for 3,000 commands using Ollama (`phi3.5`, temperature `0`, seed `42`).
  - Scaffolding of multi-worker sharding scripts and SeaweedFS S3 upload handlers.
- **Verification**:
  - `worker/verify_shards.py`: Checked that exactly 3,000 IDs were labelled across shards with zero gaps and zero duplicates.
  - `worker/clean.py`: Programmatically validated all raw replies against JSON syntax, 4-key schema, the 8 allowed intents, and slot text containment in the input command.

### Task 2: Training the Student (Sequence-Level Distillation)
- **Usage**:
  - Fine-tuning PyTorch / Transformers script (`training/train.py`) implementing causal language modeling on CPU with `bfloat16`.
  - Batch generation and loss recording across epochs (`training/loss.csv`).
- **Verification**:
  - Deterministic evaluation on `data/validation.jsonl` using `tools/score.py`.
  - Verified that trained student achieved 92.0% JSON validity (and exceeded 95% on test set) compared to 0.0% for the untrained model.

### Task 3: The Inference Service in a Container
- **Usage**:
  - FastAPI asynchronous server skeleton (`service/app.py`), endpoints (`/parse`, `/healthz`, `/readyz`), and Dockerfile.
  - S3 artifact loading at pod start-up using `boto3`.
- **Verification**:
  - Pinned all dependencies in `service/requirements.txt` to ensure reproducible builds under 2 GB.
  - Hardened output validation against `data/schema.json`.
  - Implemented and verified `FAULT_INJECT=1` returning exact HTTP 500 error `{"error": "invalid_model_output"}`.
  - Ran 50 sequential requests under cgroup limits (1 CPU, 1 GiB RAM) confirming zero OOM kills and 348 MiB peak memory.

### Task 4: Kubernetes Deployment, Scaling, and Reliability
- **Usage**:
  - Kubernetes manifest authoring (`deployment/app.yaml`, `deployment/hpa.yaml`).
  - Orchestration of rolling updates, rollback procedures, and Pod deletion recovery tests.
- **Verification**:
  - Automated Locust load testing (`tools/locustfile.py`) measuring latency (p50, p95), error rates (0.00% across updates), and round-robin load distribution across worker nodes.
  - HPA scaling test verifying automated scale-up to 2 replicas under load and scale-down to 1 when idle.

### Task 5: Subnetting and Network Access Control
- **Usage**:
  - Assisting with VLSM calculations for `10.20.0.0/16` and drafting the stateless NACL rule table in `network/nacl.json`.
- **Verification**:
  - Verified subnet boundaries, prefix lengths, and usable host counts using Python standard `ipaddress` library.
  - Simulated network packet traversal with `tools/nacl_sim.py`, achieving 100% (6/6) matching on test packets.

### Task 6: Reproducibility, Testing, and CI/CD
- **Usage**:
  - Structuring GitHub Actions workflow stages (linting, unit testing, model evaluation, quality gate, secret scanning).
  - Drafting unit test cases for data cleaning, NACL decisions, and schema validation.
- **Verification**:
  - Executed `ruff check .` with zero linting errors.
  - Executed `pytest tests/test_unit.py` with 100% pass rate.
  - Automated quality gate verification (`score.py --min-validity 95`).
  - Gitleaks secret scanning confirming zero committed credentials.

---

## 3. Guiding Principles and Human Oversight

1. **No Blind Trust**: Every code snippet, script, and configuration generated with AI assistance was reviewed line by line, tested in the local environment, and validated against assignment requirements.
2. **Deterministic Quality Gates**: Critical outputs were verified using automated scripts (`verify_shards.py`, `clean.py`, `score.py`, `nacl_sim.py`, and `pytest`) rather than subjective appraisal.
3. **Reproducibility**: All configurations, seeds (seed `42` for teacher and student v1; seed `43` for student v2), and dependencies were pinned and version-controlled.
