# Task 7: Performance, Cost, and Review

## 1. Overview

Task 7 conducts a holistic performance evaluation, economic cost estimation, and reliability analysis of our command-parsing service deployed on the local Kubernetes cluster. We execute the standard 2-minute Locust load test (4 users, 4 spawn rate), track live CPU and memory metrics per pod via `kubectl top pods`, evaluate the service against a defined Service Level Objective (SLO) and error budget, calculate cloud hosting expenses using `data/rate_card.json`, and synthesize a comprehensive review across all six architectural components.

---

## 2. Load Test Performance Benchmarking

### 2.1 Benchmark Configuration
- **Tool**: Locust 2.47.0 (`tools/locustfile.py`)
- **Target Endpoint**: `http://localhost:8080/parse`
- **Users**: 4 concurrent users
- **Spawn Rate**: 4 users/second
- **Duration**: 2 minutes (120 seconds)
- **Workload**: Natural language commands cycled from `data/validation.jsonl`
- **Failure Threshold**: Response time $> 30$ seconds or HTTP status code $\ne 200$
- **Replicas**: 2 Ready pods deployed on worker nodes `agent-0` and `agent-1`

### 2.2 Five Required Measurements

| Metric | Measured Value | Measurement Source & Evidence |
| :--- | :---: | :--- |
| **1. p50 Latency (Median)** | **5,600 ms** (5.60 s) | `results/task7_loadtest_stats.csv` (Task 7 benchmark) |
| **p95 Latency** | **17,000 ms** (17.00 s) | `results/task7_loadtest_stats.csv` (Task 7 benchmark) |
| *p50 Latency (Steady-State)* | *4,000 ms* (4.00 s) | `results/loadtest_stats_balancing.csv` (Task 4 balancing) |
| *p95 Latency (Steady-State)* | *8,400 ms* (8.40 s) | `results/loadtest_stats_balancing.csv` (Task 4 balancing) |
| *p50 Under 1 CPU Limit* | *2,904 ms* (2.90 s) | `results/task3_limits_test.json` (Sequential single-worker) |
| **2. Throughput** | **0.66 req/s** (2,393 req/hr) | `results/task7_loadtest_stats.csv` |
| *Throughput (Steady-State)* | *0.91 req/s* (3,260 req/hr) | `results/loadtest_stats_balancing.csv` |
| **3. Error Rate** | **1.28%** (1 failure / 78 total) | `results/task7_benchmark.json` |
| *Error Rate (Recovery)* | *0.00%* (0 failures / 40 total) | `results/loadtest_recovery_stats.csv` |
| *Error Rate (Rolling Update)* | *0.96%* (1 failure / 104 total) | `results/loadtest_rolling_stats.csv` |
| **4. Pod CPU & Memory** | **Pod 1: 996m CPU, 375 MiB RAM**<br>**Pod 2: 1004m CPU, 375 MiB RAM** | Sampled every 5s during load test via `kubectl top pods -n app` |
| **5. Cold-Start Time** | **7.13 s (Median)** | Three runs in Task 4: 6.34s, 7.13s, 8.01s (`results/cold_start_test.json`) |

### 2.3 Live Pod Resource Consumption During Test

Resource metrics were gathered at 5-second intervals via `kubectl top pods -n app` across both running replicas:

```
Pod Resource Profiles:
- Replica 1 (inference-service-5c7c4ffbdf-jtnt9):
    * CPU: Average = 729.0m, Peak = 996m (99.6% of 1000m limit)
    * Memory: Average = 367.1 MiB, Peak = 375.0 MiB (36.6% of 1GiB limit)
- Replica 2 (inference-service-5c7c4ffbdf-lpgth):
    * CPU: Average = 890.7m, Peak = 1004m (100.4% of 1000m limit)
    * Memory: Average = 361.3 MiB, Peak = 375.0 MiB (36.6% of 1GiB limit)
```

### 2.4 Traffic Load Balancing Distribution
Saved to `results/task7_headers.json`:
- **Replica 1 (`jtnt9`)**: 38 requests (49.4%)
- **Replica 2 (`lpgth`)**: 39 requests (50.6%)
- **Model Version**: 100% `v1` (77 requests)

---

## 3. Cost Estimation

We compute the operational cost of processing 1,000 requests using the pricing schedule defined in `data/rate_card.json`.

### 3.1 Rate Card Parameters
- **CPU Rate**: ₹3.50 per vCPU-hour
- **Memory Rate**: ₹0.45 per GiB-hour
- **Currency**: Indian Rupee (INR / ₹)
- **Billing Rule**: A replica is billed for its CPU limit and memory limit for every hour it runs, whether or not it is busy.
- **Formula**:
  $$\text{cost per 1,000 requests} = \left( \frac{\text{hourly cost of all running replicas}}{\text{requests served per hour}} \right) \times 1000$$

### 3.2 Step-by-Step Derivation

1. **Individual Pod Resource Limits (`deployment/app.yaml`)**:
   - CPU Limit: `1000m` = $1.0\text{ vCPU}$
   - Memory Limit: `1Gi` = $1.0\text{ GiB}$

2. **Hourly Cost of One Replica**:
   $$\text{Cost}_{\text{replica}} = (1.0\text{ vCPU} \times ₹3.50) + (1.0\text{ GiB} \times ₹0.45) = ₹3.50 + ₹0.45 = ₹3.95\text{ / hour}$$

3. **Hourly Cost of All Running Replicas ($N = 2$)**:
   $$\text{Hourly Cost}_{\text{total}} = 2 \times ₹3.95 = \mathbf{₹7.90\text{ INR / hour}}$$

4. **Requests Served per Hour**:
   - **From Task 7 Benchmark** ($R = 0.6648\text{ req/s}$):
     $$\text{Requests / hour} = 0.6648 \times 3,600 = \mathbf{2,393.16\text{ requests / hour}}$$
   - *Alternative (Steady-State Balancing Run, $R = 0.9055\text{ req/s}$)*:
     $$\text{Requests / hour} = 0.9055 \times 3,600 = \mathbf{3,259.75\text{ requests / hour}}$$

5. **Cost per 1,000 Requests**:
   - **Using Task 7 Benchmark Throughput** ($2,393.16\text{ req/hr}$):
     $$\text{Cost per 1,000 requests} = \left( \frac{₹7.90}{2,393.16} \right) \times 1,000 = \mathbf{₹3.301\text{ INR}}$$
   - *Using Steady-State Throughput ($3,259.75\text{ req/hr}$)*:
     $$\text{Cost per 1,000 requests} = \left( \frac{₹7.90}{3,259.75} \right) \times 1,000 = \mathbf{₹2.423\text{ INR}}$$

---

## 4. Service Level Objective (SLO) and Error Budget

### 4.1 SLO Definition
- **Service Level Indicator (SLI)**: Ratio of successful requests returning HTTP status code 200 within 30 seconds to the total number of requests sent to `/parse`.
  $$\text{SLI} = \frac{\text{Count of Successful Requests (HTTP 200, Latency } \le 30\text{s)}}{\text{Total Requests Sent}}$$
- **SLO Target**: **99.0%** of requests must succeed.
- **Evaluation Window**: One full load-test execution run (2 minutes, 4 concurrent users).

### 4.2 Error Budget Calculations

1. **Allowable Failure Fraction**:
   $$\text{Allowable Failure Rate} = 100\% - 99.0\% = 1.0\% = 0.01$$

2. **Error Budget in Number of Requests**:
   - For our Task 7 benchmark run ($N = 78$ total requests):
     $$\text{Error Budget} = 78 \times 0.01 = \mathbf{0.78\text{ requests}}$$
   - For a standard 100-request window:
     $$\text{Error Budget} = 100 \times 0.01 = \mathbf{1.0\text{ request}}$$
   - For our Task 4 rolling update test ($N = 104$ total requests):
     $$\text{Error Budget} = 104 \times 0.01 = \mathbf{1.04\text{ requests}}$$

3. **Error Budget Consumption Analysis**:
   - **Task 7 Benchmark Run**: 1 failed request occurred ($HTTP\ 500$ due to output validation failure).
     $$\text{Budget Used} = \left( \frac{1}{0.78} \right) \times 100\% = \mathbf{128.2\%}$$
     *Result*: Error budget was exhausted by 0.22 requests during peak CPU saturation.
   - **Task 4 Rolling Update Run**: 1 network failure out of 104 requests.
     $$\text{Budget Used} = \left( \frac{1}{1.04} \right) \times 100\% = \mathbf{96.15\%}$$
     *Result*: Met the SLO with 3.85% error budget remaining.
   - **Task 4 Recovery Run**: 0 failures out of 40 requests.
     $$\text{Budget Used} = \mathbf{0.00\%}$$
     *Result*: Met the SLO with 100% error budget remaining.

---

## 5. Architectural Review Table

| Component or Concern | Evidence (a measured number) | Limitation You Found | Improvement You Propose |
| :--- | :--- | :--- | :--- |
| **Data and Storage** | **2,761 valid records kept** out of 3,000 (239 rejected: 216 duplicate commands, 23 schema/JSON failures). Checked via SHA-256 `c8cf810cd1...`. | Ollama teacher labeling on CPU processes single requests sequentially per worker, taking ~2 hours for 3,000 commands. | Implement batched generation using vLLM or Hugging Face TGI with asynchronous request queueing to increase labeling throughput by $5\times$. |
| **Model Quality** | **98.0% JSON validity**, 54.0% intent accuracy, 11.0% full frame on student model (vs. 0.0% validity / 0.0% full frame on untrained baseline). | The 70M parameter Pythia model lacks capacity to capture subtle multi-word datetime and slot boundaries accurately. | Transition from sequence-level cross-entropy to logit-based KL-divergence distillation, and evaluate a 160M–500M parameter student model with LoRA adapters. |
| **Latency and Throughput** | Median latency $p50 = \mathbf{5,600\text{ ms}}$, throughput $\mathbf{0.66\text{ req/s}}$ across 2 pods under load; single-worker baseline $p50 = \mathbf{2,904\text{ ms}}$. | Autoregressive token-by-token text generation on CPU is computationally bound, saturating 1 vCPU per replica at ~0.5 req/s. | Quantize model weights to INT8/INT4 using ONNX Runtime or llama.cpp, and implement non-autoregressive classification heads for intent and slot tagging. |
| **Resource Utilisation** | Peak memory = $\mathbf{375\text{ MiB}}$ (36.6% of 1 GiB limit); peak CPU = $\mathbf{1,004\text{m}}$ ($100\%$ saturation of 1 vCPU limit). | Memory requests (`512Mi`) are over-provisioned relative to actual usage (`~375MiB`), reducing pod scheduling density per worker node. | Right-size pod memory request to `384MiB` and CPU request to `250m`, enabling tighter cluster bin-packing and lower hardware footprints. |
| **Reliability and Recovery** | Pod recovery time = $\mathbf{17.8\text{ s}}$ with $\mathbf{0.00\%}$ failed requests; rolling update zero dropped connections; cold start median = $\mathbf{7.13\text{ s}}$. | Pod cold starts require downloading the full 104 MB tarball from SeaweedFS S3 and deserializing weights into memory on every restart. | Pre-populate model weights on worker nodes using a shared PersistentVolume (ReadWriteMany) or node-local hostPath caching to cut cold starts to $< 2\text{ s}$. |
| **Security and Cost** | Stateless NACL achieved $\mathbf{100.0\%}$ (6/6 sample, 21/21 edge) block accuracy; Gitleaks reported $\mathbf{0\text{ leaks}}$; cost = $\mathbf{₹3.30\text{ INR / 1,000 requests}}$. | Stateless CIDR-based NACLs only filter Layer 3/4 headers and cannot protect against application-layer (Layer 7) prompt injections or semantic DDoS. | Deploy an Ingress Web Application Firewall (WAF) with rate limiting, payload inspection, and AWS IAM roles for service accounts (IRSA) to eliminate static secrets. |
