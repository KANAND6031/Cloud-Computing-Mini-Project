# Task 4: Kubernetes Deployment, Scaling, and Reliability

## 1. Overview and Architecture

Task 4 deploys the containerized inference service to our local `k3d` Kubernetes cluster (`cloud-assignment`), configuring resource governance, health probes, automated autoscaling, zero-downtime rolling updates, pod recovery, and cold-start benchmarking.

All resources are deployed in the dedicated `app` namespace. Inbound traffic reaches the service via the built-in Traefik Ingress controller, which is exposed to the local host on port 8080 through `k3d-cloud-assignment-serverlb`.

```
               Host Request (http://localhost:8080/parse)
                                  |
                                  v
             +-----------------------------------------+
             |      k3d Load Balancer (Port 8080:80)   |
             +-----------------------------------------+
                                  |
                                  v
             +-----------------------------------------+
             |         Traefik Ingress Controller       |
             |       (inference-ingress, ns: app)      |
             +-----------------------------------------+
                                  |
                                  v
             +-----------------------------------------+
             |       ClusterIP Service (Port 8000)     |
             |       (inference-service, ns: app)      |
             +-----------------------------------------+
                       |                       |
            (Round-Robin Balance)    (Round-Robin Balance)
                       |                       |
                       v                       v
            +--------------------+   +--------------------+
            | Pod Replica 1      |   | Pod Replica 2      |
            | (agent-0, 10.42...) |   | (agent-1, 10.42...) |
            | Readiness: /readyz |   | Readiness: /readyz |
            | Liveness: /healthz |   | Liveness: /healthz |
            | preStop: sleep 5   |   | preStop: sleep 5   |
            +--------------------+   +--------------------+
                       ^                       ^
                       \-----------+-----------/
                                   |
                 +-----------------------------------+
                 | SeaweedFS S3 Object Storage       |
                 | (seaweedfs.data:8333, ns: data)   |
                 +-----------------------------------+
```

---

## 2. Manifests and Resource Governance

The Kubernetes manifests are maintained under `deployment/app.yaml` and `deployment/hpa.yaml`:

### 2.1 Namespace and Credentials Secret
- Namespace `app` encapsulates the application plane.
- Secret `s3-credentials` supplies `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to the pods via `secretKeyRef`. No credentials are hardcoded in the deployment specification.

### 2.2 Deployment and Resource Constraints
- **Replicas**: Initialized to 2 replicas, distributed across worker nodes (`agent-0` and `agent-1`).
- **Resource Requests and Limits**:
  - `requests`: `cpu: 250m`, `memory: 512Mi`
  - `limits`: `cpu: 1000m`, `memory: 1Gi`
- **Rolling Update Strategy**:
  - `maxSurge: 1`
  - `maxUnavailable: 0`
  Guarantees that new replicas become Ready before old replicas are terminated, preventing capacity dips.
- **Graceful Draining (`preStop` Hook)**:
  - Added `lifecycle: preStop: exec: command: ["/bin/sh", "-c", "sleep 5"]` with `terminationGracePeriodSeconds: 30`.
  - When a pod is terminated, the endpoints controller removes the pod IP from service routing while the pod finishes all in-flight requests during the 5-second sleep window. This eliminates transient `502 Bad Gateway` errors.

### 2.3 Health Probes and Endpoint Readiness
- **Liveness Probe**:
  - Path: `/healthz`, port 8000.
  - Checks whether the Uvicorn web process is responsive.
- **Readiness Probe**:
  - Path: `/readyz`, port 8000.
  - Returns HTTP 503 during startup while the pod downloads weights from S3 and loads them into memory.
  - Returns HTTP 200 once the model is fully loaded and ready to serve traffic.
  - Verified from pod logs: Endpoints controller marks the pod unready and routes **zero** traffic to the pod until `/readyz` responds with HTTP 200.

---

## 3. Load Balancing Across Replicas

### 3.1 Setup and Execution
With exactly two Ready replicas (`inference-service-79f84ddc69-69b5r` and `inference-service-79f84ddc69-gvsmv`), we executed the standard 2-minute Locust load test using 4 concurrent users against `http://localhost:8080/parse`:

```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
```

### 3.2 Measured Results
The response headers (`X-Served-By` and `X-Model-Version`) were captured and saved to `results/loadtest_headers_balancing.json`:

```json
{
  "per_replica": {
    "inference-service-79f84ddc69-gvsmv": 52,
    "inference-service-79f84ddc69-69b5r": 52
  },
  "per_model_version": {
    "v1": 104
  }
}
```

| Metric | Measured Value | Requirement | Status |
|--------|----------------|-------------|--------|
| Total Successful Requests | 104 | - | - |
| Replica 1 Requests (`agent-0`) | **52 (50.0%)** | $\ge 30\%$ | **PASS** |
| Replica 2 Requests (`agent-1`) | **52 (50.0%)** | $\ge 30\%$ | **PASS** |
| Model Version Served | `v1` (100%) | `v1` | **PASS** |

Both replicas handled an identical 50.0% share of traffic, perfectly demonstrating round-robin ingress load balancing.

---

## 4. Horizontal Pod Autoscaler (HPA)

### 4.1 HPA Configuration
Defined in `deployment/hpa.yaml`:
- **Scale Target**: `Deployment/inference-service`
- **Min Replicas**: 1
- **Max Replicas**: 2
- **Target CPU Utilization**: 70% (relative to container request `cpu: 250m`, i.e., 175m)

### 4.2 Measured Scaling Evidence
We executed `tests/test_hpa.py` to monitor replica scaling under load and back down:
1. **Idle State**: HPA observed CPU utilization of 1%, scaling down to 1 replica.
2. **Load Applied**: A 4-user Locust test pushed CPU utilization to 292% (exceeding 70%).
3. **Scale-Up**: At **20.3 seconds**, HPA triggered scale-up from 1 to 2 replicas.
4. **Cool-Down**: Once the load test ceased, CPU utilization subsided to 1%. After the 30-second stabilization window, HPA scaled back down to 1 replica at **129.1 seconds**.

#### HPA Scaling Event Timeline
| Timestamp (s) | Phase | Pod Count | CPU Utilization | Observed Action |
|---------------|-------|-----------|-----------------|-----------------|
| 0.0s | Idle | 1 | 1% / 70% | Initial steady state |
| 7.0s | Load Started | 1 | 1% / 70% | Locust traffic ramping |
| 20.3s | Scale-Up | **2** | **292% / 70%** | **HPA scaled from 1 -> 2 replicas** |
| 33.9s | Under Load | 2 | 398% / 70% | 2 replicas handling load |
| 63.9s | Load Stopped | 2 | 376% / 70% | Load ends, cooldown begins |
| 111.5s | Stabilizing | 2 | 1% / 70% | CPU drops to 1% |
| 129.1s | Scale-Down | **1** | **1% / 70%** | **HPA scaled from 2 -> 1 replica** |

Complete event timeline is preserved in `results/hpa_scaling_test.json`.

---

## 5. Zero-Downtime Rolling Update and Rollback

### 5.1 Test Procedure
Under continuous Locust traffic (4 users, 130s):
1. **Update to v2**: Executed `kubectl set env deployment/inference-service -n app MODEL_VERSION=v2 MODEL_URI=s3://models/v2/model.tar.gz`.
2. **Rollout Status**: Tracked `kubectl rollout status` until all pods were updated.
3. **Rollback to v1**: Executed `kubectl rollout undo deployment/inference-service -n app` and waited for rollback completion.

### 5.2 Measured Evidence
From `results/rolling_update_test.json`:
- **Total Requests Dispatched**: 104
- **Network / Transport Failures (502/503/timeout)**: **0 (0.00%)**
- **Model Schema Rejections (HTTP 500)**: 1 (0.96%)
- **Model Versions Served During Test**:
  - `v1` before rollout: 25 requests
  - `v2` during rollout: 31 requests
  - `v1` after rollback: 48 requests
  - Total: `v1`: 73, `v2`: 31
- **Active Version After Rollback**: `v1` (verified from Deployment metadata)

```json
{
  "per_replica": {
    "inference-service-5c7c4ffbdf-t8z9d": 10,
    "inference-service-5c7c4ffbdf-bngl7": 7,
    "inference-service-5fb58c5ccf-mhkmz": 15,
    "inference-service-5fb58c5ccf-qgzwr": 16,
    "inference-service-5c7c4ffbdf-cm7tw": 30,
    "inference-service-5c7c4ffbdf-96bm8": 26
  },
  "per_model_version": {
    "v1": 73,
    "v2": 31
  }
}
```

The `maxSurge: 1` and `preStop: sleep 5` configuration ensured zero dropped connections during the dual rolling update and rollback operations.

---

## 6. Pod Failure and Recovery Under Load

### 6.1 Test Procedure
While a 4-user Locust test was actively dispatching requests:
1. Pod `inference-service-5c7c4ffbdf-96bm8` was deleted via `kubectl delete pod ...`.
2. The ReplicaSet detected the deficit and launched a replacement pod.
3. The replacement pod fetched model weights from SeaweedFS S3 and transitioned to Ready.

### 6.2 Measured Evidence
From `results/recovery_test.json`:
- **Pod Deleted**: `inference-service-5c7c4ffbdf-96bm8`
- **New Pod Created**: `inference-service-5c7c4ffbdf-t5bdh`
- **Time to Restored Replica Count**: **17.8 seconds**
- **Total Requests**: 40
- **Failed Requests**: **0 (0.00%)** (Requirement: $\le 2\%$)
- **Distribution**:
  - Remaining original pod (`cm7tw`): 22 requests
  - Terminating pod (`96bm8` before drain): 2 requests
  - Replacement pod (`t5bdh` once Ready): 16 requests

Zero requests failed during the pod termination and replacement cycle.

---

## 7. Cold-Start Measurement

### 7.1 Methodology
Cold start is defined as the elapsed time from Pod creation to the Ready condition becoming `True`. To ensure accurate measurement across 3 independent runs:
1. Replicas scaled to 0 to purge existing cached pods.
2. Replicas scaled to 1 to create an empty, uninitialized container.
3. Polled `kubectl get pod -o json` for `conditions[type=Ready].status == True`.
4. Extracted container startup logs to confirm model retrieval from S3.

### 7.2 Measured Results

| Run | Pod Identifier | Cold Start Time (s) | S3 Download & Initialization Evidence |
|-----|----------------|---------------------|---------------------------------------|
| 1 | `inference-service-5c7c4ffbdf-gqhgr` | **6.34 s** | Downloaded `s3://models/v1/model.tar.gz` from SeaweedFS S3, extracted, and loaded in 6.34s |
| 2 | `inference-service-5c7c4ffbdf-7cgzm` | **7.13 s** | Downloaded `s3://models/v1/model.tar.gz` from SeaweedFS S3, extracted, and loaded in 7.13s |
| 3 | `inference-service-5c7c4ffbdf-jtnt9` | **8.01 s** | Downloaded `s3://models/v1/model.tar.gz` from SeaweedFS S3, extracted, and loaded in 8.01s |
| **Median** | - | **7.13 s** | - |

#### Log Evidence Sample (Run 2)
```text
2026-11-06 15:22:34,812 [INFO] Preparing model from URI: s3://models/v1/model.tar.gz using S3 endpoint: http://seaweedfs.data.svc.cluster.local:8333
2026-11-06 15:22:35,005 [INFO] Downloading archive s3://models/v1/model.tar.gz...
2026-11-06 15:22:35,414 [INFO] Extracting archive...
2026-11-06 15:22:36,560 [INFO] Model v1 successfully loaded. Service is ready on port 8000!
```
Full data preserved in `results/cold_start_test.json`.

---

## 8. Limitations of the Local Cluster Setup

As required by the assignment specification, we explicitly document the following physical and architectural limitations of our local deployment:

1. **Single-Node Hardware Isolation**:
   Although our `k3d` cluster simulates a multi-node topology with one control-plane node (`server-0`) and two worker nodes (`agent-0`, `agent-1`), all nodes run as Docker containers on a single host machine (sharing the same physical CPU, RAM, and Linux kernel via WSL2).
2. **Absence of True High Availability (HA)**:
   A physical power failure, kernel crash, or hypervisor outage on the laptop will terminate all cluster nodes simultaneously. The deployment cannot demonstrate resilience against physical hardware failure, rack power loss, or cross-datacenter partition.
3. **Shared CPU Resource Contention**:
   CPU requests and limits (`250m` / `1000m`) are enforced by Linux `cgroups` on the host kernel. Under heavy aggregate host load, clock cycles are throttled across all containers, introducing artificial latency jitter that would not occur on dedicated cloud VMs.
4. **Local Network Loopback**:
   Network traffic between the Traefik ingress, inference pods, and SeaweedFS traverses the internal Docker bridge network (`k3d-cloud-assignment`), bypassing physical NICs, top-of-rack switches, and real-world WAN latency.
