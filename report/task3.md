# Task 3: The Inference Service in a Container

## 1. Overview and Architecture

Task 3 requires building and containerizing a production-ready web inference service that wraps our fine-tuned student model (Pythia-70M) inside a lightweight container. The service listens on port 8000 and provides endpoints for command parsing, liveness checking, and readiness verification. Crucially, the container image contains **no model weights**; instead, weights are pulled dynamically from SeaweedFS S3 object storage at container startup using credentials supplied via Kubernetes Secrets.

```
                    +------------------------------------------+
                    |          Container (Port 8000)           |
                    |                                          |
  GET /healthz ---->|  Liveness Probe (HTTP 200)               |
                    |                                          |
  GET /readyz  ---->|  Readiness Probe (HTTP 503 -> 200)       |
                    |    ^ (Background Download & Init)        |
                    |    |                                     |
  POST /parse  ---->|  FastAPI + Pythia-70M (bfloat16)         |
                    |    |                                     |
                    |    v                                     |
                    |  Output Validation (schema.json)         |
                    |    |--> HTTP 200: 4-key JSON             |
                    |    \--> HTTP 500: {"error": ...}         |
                    +------------------------------------------+
                                     ^
                                     | Downloads at startup
                                     v
                       +---------------------------+
                       | SeaweedFS S3 Object Store |
                       | (s3://models/v1/model.tgz)|
                       +---------------------------+
```

---

## 2. API Design and Response Specifications

The service is implemented in `service/app.py` using FastAPI and Uvicorn.

### 2.1 Endpoints

1. **`POST /parse`**:
   - **Request Body**: `{"text": "<command>"}`
   - **Success (HTTP 200)**: Returns exactly the 4-key JSON object conforming to `schema.json`:
     ```json
     {"intent": "alarm_set", "date": "tomorrow", "time": "seven thirty am", "place": null}
     ```
   - **Response Headers**:
     - `X-Model-Version`: Configured model version (`v1` or `v2`).
     - `X-Served-By`: Pod name / container hostname (`HOSTNAME` or `socket.gethostname()`).
   - **Failure (HTTP 500)**: If the raw model output fails JSON parsing or violates `schema.json`, returns:
     ```json
     {"error": "invalid_model_output"}
     ```
     The service **never** returns malformed JSON with HTTP 200.

2. **`GET /healthz`**:
   - Liveness probe. Returns HTTP 200 with `{"status": "ok"}` as long as the Uvicorn process is alive.

3. **`GET /readyz`**:
   - Readiness probe. Model download and weight initialization occur on a background worker thread upon startup.
   - Returns **HTTP 503** `{"status": "loading"}` while model download/loading is in progress.
   - Returns **HTTP 200** `{"status": "ready"}` once weights are loaded into memory and ready for inference.

---

## 3. Configuration and Dynamic Model Loading

All configuration is externalized into environment variables:

| Environment Variable | Description | Example / Default |
|----------------------|-------------|-------------------|
| `MODEL_URI` | S3 URI of model weights archive or prefix | `s3://models/v1/model.tar.gz` |
| `MODEL_VERSION` | Version tag served and reported in headers | `v1` |
| `S3_ENDPOINT` | SeaweedFS S3 endpoint URL | `http://seaweedfs.data.svc.cluster.local:8333` |
| `MAX_NEW_TOKENS` | Max generated tokens for causal LM | `64` |
| `FAULT_INJECT` | Test flag: when `1`, forces model output to `"not json"` | `0` |

### 3.1 Object Storage Retrieval

At start-up, the container:
1. Connects to `S3_ENDPOINT` using `boto3`. Credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) are read strictly from environment variables injected via Kubernetes Secret (no hardcoded keys).
2. Parses `MODEL_URI` (e.g. `s3://models/v1/model.tar.gz`).
3. Downloads the archive and unpacks it into `/tmp/model_cache/<MODEL_VERSION>`.
4. Loads `AutoTokenizer` and `AutoModelForCausalLM` using `torch_dtype=torch.bfloat16`.
5. Sets `is_ready = True`, flipping `/readyz` from 503 to 200.

Zero model weights are stored in the Docker image.

---

## 4. Output Schema Validation and Fault Injection

### 4.1 Schema Validation

Every model prediction is validated against `data/schema.json` via `validate_output()`:
1. Must parse as valid JSON.
2. Must be an object (`dict`) with **exactly** four keys: `{"intent", "date", "time", "place"}`.
3. `intent` must belong to the 8 valid intents:
   `alarm_set`, `alarm_query`, `calendar_set`, `calendar_query`, `calendar_remove`, `weather_query`, `datetime_query`, `recommendation_events`.
4. Slot values (`date`, `time`, `place`) must be either `str` or `None`.
5. Checked against `jsonschema.validate()` using `data/schema.json["json_schema"]`.

If validation fails, the service returns HTTP 500 `{"error": "invalid_model_output"}`.

### 4.2 Fault Injection Testing

When `FAULT_INJECT=1`, `service/app.py` replaces the model output with `"not json"` before schema validation:

```powershell
docker run -d --name service-fault -p 8001:8000 `
  -e MODEL_URI="s3://models/v1/model.tar.gz" `
  -e MODEL_VERSION="v1" `
  -e S3_ENDPOINT="http://host.docker.internal:8333" `
  -e FAULT_INJECT="1" `
  cloud-service:v1
```

**Verification Evidence**:
```http
POST /parse
Body: {"text": "what is the weather in london"}

HTTP/1.1 500 Internal Server Error
date: Fri, 06 Nov 2026 14:25:50 GMT
server: uvicorn
content-length: 32
content-type: application/json
x-model-version: v1
x-served-by: 1ed67233f820

{"error": "invalid_model_output"}
```
Both response headers (`X-Model-Version` and `X-Served-By`) are preserved even on HTTP 500 errors.

---

## 5. Container Image Optimization and Size

### 5.1 Image Optimization

Standard PyTorch wheels from PyPI bundle CUDA 12.x drivers and GPU runtimes, totaling over 2.6 GB. To satisfy the strict $\le 2\text{ GB}$ limit:
- Used `python:3.11-slim` as base.
- Installed CPU-only PyTorch wheel via:
  ```bash
  pip install --no-cache-dir torch==2.2.2 --index-url https://download.pytorch.org/whl/cpu
  ```
- PyTorch CPU wheel is only **186.8 MB**.
- Dependencies pinned in `service/requirements.txt`:
  ```text
  fastapi==0.110.0
  uvicorn==0.28.0
  torch==2.2.2
  transformers==4.46.3
  tokenizers==0.20.3
  numpy==1.26.4
  boto3==1.34.64
  pydantic==2.6.4
  jsonschema==4.21.1
  ```

### 5.2 Size Evidence

```powershell
$ docker images cloud-service:v1
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
cloud-service:v1   a3091816c341       1.63GB          351MB        
```
- **Total Compressed Content Size**: **351 MB**
- **Uncompressed Virtual Size**: **1.63 GB** (well below the 2.0 GB limit)

---

## 6. Running Under Limits Test (50 Sequential Requests)

### 6.1 Setup

The container was launched under the exact required resource constraints:
- **CPU limit**: `1 core` (`--cpus=1` / `1000000000 NanoCpus`)
- **Memory limit**: `1 GiB` (`--memory=1g` / `1073741824 bytes`)

```powershell
docker run -d --name service-test `
  --cpus=1 --memory=1g `
  -p 8000:8000 `
  -e MODEL_URI="s3://models/v1/model.tar.gz" `
  -e MODEL_VERSION="v1" `
  -e S3_ENDPOINT="http://host.docker.internal:8333" `
  -e MAX_NEW_TOKENS=64 `
  -e AWS_ACCESS_KEY_ID="any" `
  -e AWS_SECRET_ACCESS_KEY="any" `
  cloud-service:v1
```

Verification of container constraints via `docker inspect`:
```json
{
  "HostConfig": {
    "NanoCpus": 1000000000,
    "Memory": 1073741824
  }
}
```

### 6.2 Test Execution and Memory Monitoring

The automated test script `tests/test_under_limits.py` was executed. It spawned a background sampling thread polling `docker stats --no-stream` every 200 ms while dispatching 50 sequential requests drawn from `data/validation.jsonl`.

### 6.3 Measured Results

| Metric | Measured Value | Requirement / Limit |
|--------|----------------|---------------------|
| Total Requests | 50 | 50 |
| Successful (HTTP 200) | 46 (92.0%) | Valid outputs served |
| Schema Rejected (HTTP 500) | 4 (8.0%) | Broken outputs safely rejected |
| OOM Kills | **0** | **0 (No crash)** |
| Container Status | **Alive & Healthy** | Running |
| **Peak Memory Consumption** | **348.10 MiB** | **$\le 1,024\text{ MiB}$ (33.9% of limit)** |
| Median Latency (p50) | 2,904.73 ms | On CPU with 1 core limit |
| 95th Percentile Latency (p95) | 3,692.98 ms | On CPU with 1 core limit |
| Header `X-Served-By` | 100% present (`b1eb0568da75`) | Required |
| Header `X-Model-Version` | 100% present (`v1`) | Required |

### 6.4 Command Output Evidence

```text
============================================================
Task 3: Under-Limits Sequential 50 Requests Test
Container: service-test (1 CPU, 1 GiB memory limit)
============================================================

1. Verifying probes...
  /healthz returned HTTP 200 OK
  /readyz returned HTTP 200 OK

2. Sending 50 requests sequentially to http://localhost:8000/parse...
  Completed 10/50 requests | Latency: 2796.8ms | Status: 200 | Peak Mem: 339.8 MiB
  Completed 20/50 requests | Latency: 3405.7ms | Status: 200 | Peak Mem: 342.4 MiB
  Completed 30/50 requests | Latency: 2701.2ms | Status: 200 | Peak Mem: 343.2 MiB
  Completed 40/50 requests | Latency: 3111.3ms | Status: 200 | Peak Mem: 345.1 MiB
  Completed 50/50 requests | Latency: 3299.6ms | Status: 200 | Peak Mem: 348.1 MiB

============================================================
TEST SUMMARY
============================================================
Total Requests: 50
Successful (HTTP 200): 46
OOM Killed: False
Container Alive: True
Peak Memory: 348.10 MiB (348.1MiB / 1GiB)
p50 Latency: 2904.73 ms
p95 Latency: 3692.98 ms
Served By Header: {'b1eb0568da75': 50}
Model Version Header: {'v1': 50}

Docker stats snapshot:
CONTAINER ID   NAME           CPU %     MEM USAGE / LIMIT   MEM %     NET I/O          BLOCK I/O       PIDS
b1eb0568da75   service-test   0.19%     347.1MiB / 1GiB     33.90%    124MB / 3.01MB   430kB / 254MB   25

Report written to results/task3_limits_test.json
```

All metrics and raw statistics are archived in `results/task3_limits_test.json`.
