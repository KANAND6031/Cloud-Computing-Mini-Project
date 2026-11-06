# Task 1: Object Storage and Parallel Teacher Labelling

## 1. Architecture and Setup

### 1.1 Kubernetes Cluster Environment
A lightweight, multi-node local Kubernetes cluster was created using `k3d` configured via `cluster/k3d.yaml`.
- **Control-plane node**: `k3d-cloud-assignment-server-0` (v1.35.5+k3s1)
- **Worker agent nodes**: `k3d-cloud-assignment-agent-0`, `k3d-cloud-assignment-agent-1`
- **Load Balancer Proxy**: `k3d-cloud-assignment-serverlb`, exposing host port 8080 to the internal Traefik ingress controller on port 80.

### 1.2 Object Storage Deployment (SeaweedFS)
SeaweedFS was deployed in the dedicated namespace `data` as a Kubernetes Deployment (`deployment/seaweedfs.yaml`) backed by a PersistentVolumeClaim (`seaweedfs-pvc`) using K3s local-path storage.
- **Service Endpoint**: `http://seaweedfs.data.svc.cluster.local:8333` (accessible inside the cluster) and port-forwarded to `http://127.0.0.1:8333` for local host access.
- **Buckets Created**:
  1. `datasets`: Holds `commands_pool.jsonl`, raw teacher shard objects (`teacher/shard-0.jsonl`, `teacher/shard-1.jsonl`), and cleaned training datasets (`v1/train.jsonl`, `v1/train.sha256`).
  2. `models`: Initialized to hold student model artifacts (`models/v1/`, `models/v2/`).

### 1.3 Teacher Model Configuration
The teacher model `phi3.5` (Microsoft Phi-3.5-mini-instruct, 3.8B parameters) was run with Ollama on the host machine listening on all interfaces (`OLLAMA_HOST=0.0.0.0:11434`), accessible from cluster pods via `http://host.k3d.internal:11434`.
Deterministic inference settings were strictly enforced:
- `temperature`: 0
- `seed`: 42
- `format`: "json"
- **Prompt**: Kept in `prompts/teacher_prompt.txt`, asking for the four-key JSON contract (`intent`, `date`, `time`, `place`) with slot extraction rules.

---

## 2. Sharding Strategy and Parallel Processing

### 2.1 Mathematical Formulation of Sharding
To parallelize labelling across multiple concurrent workers without inter-process locking or duplicate work, deterministic modulo partitioning over 0-indexed line numbers is employed:
$$\text{Assigned if } \text{LineIndex} \pmod{\text{SHARD\_COUNT}} = \text{SHARD\_INDEX}$$
For $N = 3,000$ commands and $\text{SHARD\_COUNT} = 2$:
- **Worker 0** (`SHARD_INDEX = 0`): Processes even line numbers ($0, 2, 4, \dots, 2998$) $\rightarrow$ exactly 1,500 commands.
- **Worker 1** (`SHARD_INDEX = 1`): Processes odd line numbers ($1, 3, 5, \dots, 2999$) $\rightarrow$ exactly 1,500 commands.

### 2.2 Guarantees and Load Balancing
- **Partitioning Completeness (No Gaps)**: Every integer $k \in [0, 2999]$ has a unique residue modulo 2 ($k \bmod 2 \in \{0, 1\}$). Hence, the union of assigned subsets is the entire dataset.
- **Disjointness (No Repeats)**: Since $k \bmod 2$ cannot simultaneously be 0 and 1, the intersection between shard partitions is strictly empty ($\emptyset$).
- **Uniform Load Distribution**: Sentences in the dataset are randomly ordered with respect to length and complexity; distributing alternating lines achieves near-identical computational load across both workers.

### 2.3 Kubernetes Pipeline Execution
Two worker jobs (`worker-shard-0` and `worker-shard-1`) were launched simultaneously in namespace `pipeline`. Each worker containerized in `cloud-worker:latest` queried the teacher, streamed outputs, and on completion uploaded:
- `datasets/teacher/shard-0.jsonl` (1,500 records)
- `datasets/teacher/shard-1.jsonl` (1,500 records)

Verification via `worker/verify_shards.py` confirmed all 3,000 unique IDs were present with 0 missing and 0 repeats.

---

## 3. Data Cleaning and Integrity

### 3.1 Cleaning Pipeline (`worker/clean.py`)
`worker/clean.py` reads all shard outputs, applies the five validation checks in strict priority order, sorts kept records in ID order, and calculates the SHA-256 digest:

| Category | Description | Count |
| :--- | :--- | :--- |
| **Input Records** | Total records read across shards | **3,000** |
| **(a) Not valid JSON** | Failed JSON parsing or not a JSON object | 0 |
| **(b) Invalid keys** | Keys do not match `{"intent", "date", "time", "place"}` exactly | 14 |
| **(c) Invalid intent** | Intent not one of the 8 allowed classes | 3 |
| **(d) Hallucinated slot** | Slot value neither null nor verbatim substring in command | 175 |
| **(e) Duplicate commands** | Duplicate command text (kept lowest ID) | 47 |
| **Records Kept** | Successfully cleaned training samples | **2,761** |

$$\text{Sum Check: } 0 + 14 + 3 + 175 + 47 + 2,761 = 3,000 \quad (\text{Exact Match})$$

### 3.2 SHA-256 Checksum
The cleaned dataset was written to `datasets/v1/train.jsonl` and uploaded to SeaweedFS S3 at `s3://datasets/v1/train.jsonl`.
The recorded SHA-256 digest in `datasets/v1/train.sha256` is:
```
c8cf810cd1d4ee304c5b04ee629a3523dcd8c211674201abd3749d72a9fdead6
```
Running `worker/clean.py` deterministically reproduces this identical checksum.
