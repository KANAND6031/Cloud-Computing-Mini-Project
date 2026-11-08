# Task 6: Reproducibility, Testing, and CI/CD

## 1. Overview and Pipeline Architecture

Task 6 establishes end-to-end reproducibility, rigorous automated testing, and a production-grade Continuous Integration / Continuous Delivery (CI/CD) workflow. The repository is configured to build and deploy the complete local cloud environment from scratch with a single command, run linting and unit testing, perform automated model evaluation against release artifacts, enforce quality gates, and scan for secret leakage.

```
                          GitHub Actions CI Workflow (.github/workflows/ci.yaml)
+------------------------------------------------------------------------------------------------+
|  0. Gitleaks Secret Scanner -> Scans git commit history for credentials (0 leaks detected)    |
+------------------------------------------------------------------------------------------------+
                                               |
                                               v
+------------------------------------------------------------------------------------------------+
|  1. Linting Stage           -> ruff check . (Strict syntax, import, and PEP8 compliance)       |
+------------------------------------------------------------------------------------------------+
                                               |
                                               v
+------------------------------------------------------------------------------------------------+
|  2. Unit Test Stage         -> pytest -v tests/test_unit.py (4 unit tests passed)              |
|                                - Data cleaning filtering rules (clean.py)                      |
|                                - Stateless NACL simulator & rule ordering (nacl.json)          |
|                                - Schema & fault injection validation (schema.json)             |
|                                - VLSM subnet calculations & contiguity (subnets.md)            |
+------------------------------------------------------------------------------------------------+
                                               |
                                               v
+------------------------------------------------------------------------------------------------+
|  3. Model Evaluation Stage  -> Download v1.0.0 release asset (model.tar.gz) from GitHub        |
|                                - Verify SHA-256 matches models/v1/model.sha256                 |
|                                - Evaluate on validation.jsonl (100 commands)                   |
|                                - Run tools/score.py predictions.jsonl validation.jsonl         |
+------------------------------------------------------------------------------------------------+
                                               |
                                               v
+------------------------------------------------------------------------------------------------+
|  4. Quality Gate Stage      -> tools/score.py --min-validity 95                                |
|                                - Student Model: 98.0% validity -> [ PASS ]                     |
|                                - Untrained Model: 0.0% validity -> [ FAIL & BLOCK PIPELINE ]   |
+------------------------------------------------------------------------------------------------+
```

---

## 2. Reproducibility: `make up` and `make down`

Per project requirements, the entire cloud system can be built and deployed from a fresh clone in at most three commands (implemented in a single command: `make up`).

### 2.1 Workflow Commands
- **`make up`**:
  1. Creates the local Kubernetes cluster `cloud-assignment` from `cluster/k3d.yaml` with server load-balancing and port 8080 mapping.
  2. Deploys SeaweedFS in the `data` namespace (`deployment/seaweedfs.yaml`) and waits for readiness.
  3. Checks local model artifacts; if not present, downloads the release asset `model.tar.gz` directly from GitHub Releases (`v1.0.0`).
  4. Bootstraps SeaweedFS S3 buckets (`datasets` and `models`) and uploads dataset pool and student model weights.
  5. Builds the service container image (`cloud-service:v1`) and imports it into the `k3d` cluster nodes.
  6. Deploys the inference service, ingress routing, and HorizontalPodAutoscaler (`deployment/app.yaml` & `deployment/hpa.yaml`).
  7. Waits for pod readiness and verifies service availability at `http://localhost:8080/parse`.
- **`make down`**:
  - Deletes the `cloud-assignment` k3d cluster and cleans up all associated container volumes and port mappings:
    ```bash
    k3d cluster delete cloud-assignment
    ```
- **`make train`**: Executes sequence-level student distillation (`training/train.py`), supporting `SUBSET=50`.
- **`make test`**: Runs unit test suite (`pytest -v tests/test_unit.py`).
- **`make lint`**: Runs code quality checks (`ruff check .`).

---

## 3. Automated Code Quality & Unit Testing

### 3.1 Linting (`ruff check .`)
All code in the repository is configured via `pyproject.toml` to comply with PEP8 standards, type hygiene, and modern Python guidelines. Unused imports, ambiguous variable names, and improper exception handling were audited and remediated. The linter executes cleanly:
```bash
$ ruff check .
All checks passed!
```

### 3.2 Unit Test Suite (`pytest -v tests/test_unit.py`)
Four comprehensive unit tests were constructed in `tests/test_unit.py` requiring zero external cloud dependencies:

1. **`test_clean_validation_rules`**: Validates that `clean.py` filters enforce requirements (a) through (e):
   - Malformed/truncated JSON strings are rejected;
   - Missing or superfluous keys outside the required 4-tuple are rejected;
   - Unsupported intents not in the 8 allowed categories are rejected;
   - Hallucinated slot values absent from the input command text are rejected;
   - Valid records parse successfully with slot values properly verified.
2. **`test_nacl_stateless_rules`**: Validates the public subnet NACL simulation:
   - Inbound HTTP/HTTPS from `0.0.0.0/0` is permitted;
   - Inbound traffic from abusive CIDR `198.51.100.0/24` is dropped by Rule 100 before web allow rules;
   - Inbound SSH (port 22) is permitted exclusively from `management` (`10.20.5.128/27`) and blocked from external IPs;
   - Outbound traffic to `app` on port 8000 and return client responses on ephemeral ports (1024–65535) are permitted.
3. **`test_schema_and_fault_injection`**: Validates service output checking against `data/schema.json` and verifies that non-JSON strings (simulating `FAULT_INJECT=1`) trigger immediate validation failure.
4. **`test_subnet_vlsm_math`**: Validates that all four subnets (`app`, `public`, `data`, `management`) are contiguous, non-overlapping, aligned to power-of-two boundaries within `10.20.0.0/16`, and meet their respective host capacities.

```bash
$ pytest -v tests/test_unit.py
tests/test_unit.py::test_clean_validation_rules PASSED                   [ 25%]
tests/test_unit.py::test_nacl_stateless_rules PASSED                     [ 50%]
tests/test_unit.py::test_schema_and_fault_injection PASSED               [ 75%]
tests/test_unit.py::test_subnet_vlsm_math PASSED                         [100%]
============================== 4 passed in 0.05s ==============================
```

---

## 4. Release Asset & Model Evaluation Stage

The distilled student model (`models/v1/`) is published as a GitHub Release asset:
- **Release Tag**: `v1.0.0` (`https://github.com/KANAND6031/cloud/releases/tag/v1.0.0`)
- **Published Asset**: `model.tar.gz`
- **SHA-256 Checksum**: `dbc2a82188fff0df1ca8c8ab67cbfb9f5c79258e48036861978438260b80bae6` (recorded in `models/v1/model.sha256`).

During Stage 3 of CI:
1. The GitHub runner downloads `model.tar.gz` and `model.sha256` via `gh release download`.
2. Verifies the SHA-256 hash using `sha256sum -c model.sha256`.
3. Unpacks the archive and evaluates predictions against `data/validation.jsonl` using `training/evaluate_ci.py`.
4. Executes `python tools/score.py results/predictions.jsonl data/validation.jsonl --out results/ci_evaluation_report.json`.

---

## 5. Quality Gate Enforcement & Deliberately Failing Run

The quality gate ensures that no regression compromises service contract integrity by enforcing:
```bash
python tools/score.py results/predictions.jsonl data/validation.jsonl --min-validity 95
```

### 5.1 Fine-Tuned Student Model (Gate Passed)
The distilled student model achieves **98.0% JSON validity**, successfully passing the threshold:
```json
{
  "json_validity": 98.0,
  "intent_accuracy": 54.0,
  "date_accuracy": 50.0,
  "time_accuracy": 71.0,
  "place_accuracy": 78.0,
  "full_frame": 11.0,
  "examples": 100,
  "missing_predictions": 0
}
```

### 5.2 Deliberately Failing Run (Gate Rejected)
To prove that the gate prevents invalid models from progressing, the workflow was executed with `test_bad_model=true`, simulating an untrained model producing unstructured text:

```text
QUALITY GATE FAILED: json_validity 0.0 < 95.0
{
  "json_validity": 0.0,
  "intent_accuracy": 0.0,
  "date_accuracy": 0.0,
  "time_accuracy": 0.0,
  "place_accuracy": 0.0,
  "full_frame": 0.0,
  "examples": 100,
  "missing_predictions": 0
}
Process completed with exit code 1.
```

- **Link to Failed Quality Gate Run**: `[Pending GitHub Actions Run Link]`
- **Behavior**: The job immediately terminated at Stage 4 with non-zero exit code, blocking downstream deployment.

---

## 6. Secret Scanning (Gitleaks)

In compliance with project security guidelines ("Do not store credentials, keys, or passwords in the repository"), automated secret scanning was integrated into both local developer tooling and the GitHub Actions workflow using official Gitleaks:

```bash
$ docker run --rm -v "${PWD}:/path" zricethezav/gitleaks:latest detect --source="/path" --verbose
7:09AM INF 5 commits scanned.
7:09AM INF scanned ~8948252 bytes (8.95 MB) in 7.13s
7:09AM INF no leaks found
```
**Result**: 0 secrets, passwords, or cloud API tokens detected across all commits.

---

## 7. AI Usage Disclosure

Comprehensive documentation of all AI tools, models, generated components, and human verification methodologies is maintained in [`AI_USE.md`](file:///c:/Users/krish/Downloads/cloud/AI_USE.md).
