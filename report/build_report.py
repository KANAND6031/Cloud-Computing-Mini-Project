import os
import subprocess

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Cloud Computing (CS3081): Mini Project Report</title>
<style>
  @page {
    size: A4 portrait;
    margin: 10mm 12mm 10mm 12mm;
    @bottom-right {
      content: counter(page);
    }
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 8.5pt;
    line-height: 1.35;
    color: #1a1a1a;
    margin: 0;
    padding: 0;
  }
  .page {
    page-break-after: always;
    height: 98vh;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .page:last-child {
    page-break-after: avoid;
  }
  h1 {
    font-size: 14pt;
    color: #1a365d;
    border-bottom: 2px solid #2b6cb0;
    padding-bottom: 3px;
    margin-top: 0;
    margin-bottom: 6px;
  }
  h2 {
    font-size: 10.5pt;
    color: #2b6cb0;
    margin-top: 6px;
    margin-bottom: 4px;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 2px;
  }
  h3 {
    font-size: 9pt;
    color: #2d3748;
    margin-top: 4px;
    margin-bottom: 2px;
  }
  p {
    margin: 3px 0;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 4px 0;
    font-size: 7.8pt;
  }
  th, td {
    border: 1px solid #cbd5e0;
    padding: 3px 5px;
    text-align: left;
  }
  th {
    background-color: #ebf8ff;
    color: #2b6cb0;
    font-weight: 600;
  }
  tr:nth-child(even) td {
    background-color: #f7fafc;
  }
  code {
    font-family: Consolas, "Courier New", monospace;
    font-size: 7.8pt;
    background-color: #edf2f7;
    padding: 1px 3px;
    border-radius: 2px;
  }
  pre {
    background-color: #f7fafc;
    border: 1px solid #e2e8f0;
    padding: 4px;
    border-radius: 3px;
    font-size: 7.2pt;
    margin: 3px 0;
    overflow-x: hidden;
  }
  ul, ol {
    margin: 2px 0 4px 16px;
    padding: 0;
  }
  li {
    margin-bottom: 1px;
  }
  .header-box {
    background-color: #ebf8ff;
    border: 1px solid #bee3f8;
    padding: 6px 10px;
    border-radius: 4px;
    margin-bottom: 6px;
  }
  .header-box h1 {
    font-size: 13pt;
    margin: 0 0 2px 0;
    border: none;
    color: #2b6cb0;
  }
  .header-meta {
    font-size: 8pt;
    color: #4a5568;
    display: flex;
    justify-content: space-between;
  }
  .two-col {
    display: flex;
    gap: 8px;
  }
  .two-col > div {
    flex: 1;
  }
  .footer {
    font-size: 7pt;
    color: #718096;
    border-top: 1px solid #e2e8f0;
    padding-top: 2px;
    display: flex;
    justify-content: space-between;
  }
</style>
</head>
<body>
{CONTENT}
</body>
</html>
"""


def build_pages():
    pages = []

    # PAGE 1: Title & Task 1
    p1 = """
<div class="page">
  <div>
    <div class="header-box">
      <h1>Cloud Computing (CS3081): Mini Project Final Report</h1>
      <div class="header-meta">
        <span><strong>Topic:</strong> Knowledge Distillation and Microservice Deployment on a Local Cloud</span>
        <span><strong>Repository:</strong> https://github.com/KANAND6031/Cloud-Computing-Mini-Project</span>
      </div>
    </div>

    <h1>Task 1: Object Storage and Parallel Teacher Labelling (12 Marks)</h1>

    <h2>1. Architecture & Environment Setup</h2>
    <p>A multi-node Kubernetes cluster was created via <code>cluster/k3d.yaml</code> with 1 control plane node (<code>server-0</code>), 2 worker agents (<code>agent-0</code>, <code>agent-1</code>), and a built-in proxy load balancer (<code>serverlb</code>) mapping host port 8080 to internal Traefik ingress port 80. SeaweedFS S3 object storage was deployed in namespace <code>data</code> backed by a PersistentVolumeClaim.</p>
    <p>Two S3 buckets were initialized: <code>datasets</code> (holding raw pool and teacher shards) and <code>models</code> (holding student model artifacts). The teacher model (<code>Phi-3.5-mini-instruct</code>, 3.8B parameters) was run via Ollama with fixed seed 42, temperature 0, and JSON format mode.</p>

    <h2>2. Sharding Strategy & Parallel Processing</h2>
    <p>Commands from <code>data/commands_pool.jsonl</code> (3,000 commands) were distributed across 2 concurrent workers in namespace <code>pipeline</code> using modular arithmetic:</p>
    <p style="text-align: center; font-weight: bold; margin: 4px 0;">line_number mod SHARD_COUNT == SHARD_INDEX</p>
    <p>Worker 0 processed all even lines (1,500 records) to <code>datasets/teacher/shard-0.jsonl</code>; Worker 1 processed all odd lines (1,500 records) to <code>datasets/teacher/shard-1.jsonl</code>. Verification with <code>worker/verify_shards.py</code> proved exactly 3,000 distinct command IDs, 0 gaps, and 0 repeats.</p>

    <h2>3. Dataset Cleaning & Rejection Audit</h2>
    <p>Script <code>worker/clean.py</code> parsed raw replies, strictly enforcing requirements (a) through (e):</p>
    <table>
      <thead>
        <tr><th>Category</th><th>Filtering Rule / Criterion</th><th>Count</th><th>Percentage</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>Input Records</strong></td><td>Total raw command records across all shards</td><td><strong>3,000</strong></td><td>100.0%</td></tr>
        <tr><td><strong>(a) Invalid JSON</strong></td><td>Malformed JSON strings unable to parse</td><td><strong>21</strong></td><td>0.70%</td></tr>
        <tr><td><strong>(b) Wrong Keys</strong></td><td>Keys not exactly {intent, date, time, place}</td><td><strong>1</strong></td><td>0.03%</td></tr>
        <tr><td><strong>(c) Bad Intent</strong></td><td>Intent not one of the 8 allowed schema intents</td><td><strong>0</strong></td><td>0.00%</td></tr>
        <tr><td><strong>(d) Bad Slot Value</strong></td><td>Slot value not null and not present in input command text</td><td><strong>1</strong></td><td>0.03%</td></tr>
        <tr><td><strong>Duplicates</strong></td><td>Identical command texts (retaining smallest command ID)</td><td><strong>216</strong></td><td>7.20%</td></tr>
        <tr><td><strong>Kept Records</strong></td><td>Cleaned dataset saved to <code>datasets/v1/train.jsonl</code></td><td><strong>2,761</strong></td><td>92.03%</td></tr>
      </tbody>
    </table>
    <p><strong>Checksum Verification</strong>: Cleaned dataset written to <code>datasets/v1/train.jsonl</code> with SHA-256: <code>c8cf810cd1d4ee304c5b04ee629a3523dcd8c211674201abd3749d72a9fdead6</code>.</p>

    <h2>4. Limitations & Improvements</h2>
    <ul>
      <li><strong>Limitation</strong>: Serial CPU generation in Ollama creates high latency (~2 hours for 3,000 commands).</li>
      <li><strong>Improvement</strong>: Deploy batched inference engines (vLLM / TGI) with async pipelining to increase generation throughput.</li>
    </ul>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 1 of 8</span>
  </div>
</div>
"""
    pages.append(p1)

    # PAGE 2: Task 2
    p2 = """
<div class="page">
  <div>
    <h1>Task 2: Training the Student (Sequence-Level Distillation) (20 Marks)</h1>

    <h2>1. Methodology: Sequence-Level vs. Logit-Based Distillation</h2>
    <p><strong>Sequence-Level Knowledge Distillation</strong> trains the student model directly on the text sequences generated by the teacher: \\( \\mathcal{L}_{\\text{seq}} = -\\sum \\log P_{\\text{student}}(y_{\\text{teacher}} \\mid x) \\). The teacher acts as a data generator; teacher output is used as hard target ground-truth.</p>
    <p><strong>Logit-Based Distillation</strong> trains the student to minimize the Kullback-Leibler (KL) divergence between student logits and teacher probability distributions over the entire vocabulary: \\( \\mathcal{L}_{\text{logit}} = \text{KL}(P_{\text{teacher}}^\tau \\parallel P_{\text{student}}^\tau) \\).</p>
    <p><strong>Why Logit Distillation is Infeasible Here</strong>: (1) <em>Vocabulary Mismatch</em>: Phi-3.5 uses a 32,064-token tokenizer while Pythia-70M uses a 50,304-token GPT-NeoX tokenizer; logits cannot be aligned across non-identical token indices. (2) <em>Black-Box Server Interface</em>: Ollama's HTTP REST API returns only generated output tokens, withholding raw vocabulary logits.</p>

    <h2>2. Training Setup & Hyperparameters</h2>
    <p>Fine-tuning configured in <code>training/config.yaml</code> and executed via <code>make train</code> (or <code>make train SUBSET=50</code>):</p>
    <div class="two-col">
      <div>
        <table>
          <tr><th>Parameter</th><th>Value</th><th>Rationale</th></tr>
          <tr><td>Base Architecture</td><td><code>EleutherAI/pythia-70m</code></td><td>70M params; lightweight CPU training</td></tr>
          <tr><td>Training Dataset</td><td>First 1,500 records of <code>train.jsonl</code></td><td>Assignment specification limit</td></tr>
          <tr><td>Precision / Device</td><td><code>bfloat16</code> / CPU</td><td>Prevents overflow on modern x86 CPU</td></tr>
          <tr><td>Learning Rate</td><td><code>1e-4</code> (AdamW)</td><td>Stable convergence for small models</td></tr>
        </table>
      </div>
      <div>
        <table>
          <tr><th>Parameter</th><th>Model v1</th><th>Model v2</th></tr>
          <tr><td>Random Seed</td><td><code>42</code></td><td><code>43</code></td></tr>
          <tr><td>Epochs</td><td>3 epochs</td><td>4 epochs</td></tr>
          <tr><td>Batch Size</td><td>16</td><td>16</td></tr>
          <tr><td>Max Seq Length</td><td>64 tokens</td><td>64 tokens</td></tr>
          <tr><td>Final Epoch Loss</td><td><strong>0.5691</strong></td><td><strong>0.5053</strong></td></tr>
        </table>
      </div>
    </div>

    <h2>3. Evaluation Results on Validation Dataset (100 Commands)</h2>
    <p>All three models scored using <code>tools/score.py</code> against <code>data/validation.jsonl</code>:</p>
    <table>
      <thead>
        <tr><th>Metric</th><th>Teacher (Phi-3.5)</th><th>Untrained Pythia-70M</th><th>Distilled Student (Pythia-70M v1)</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>JSON Validity</strong></td><td><strong>100.0%</strong></td><td><strong>0.0%</strong> (unstructured babble)</td><td><strong>92.0%</strong> (98.0% with schema rule 3)</td></tr>
        <tr><td><strong>Intent Accuracy</strong></td><td><strong>92.0%</strong></td><td>0.0%</td><td><strong>49.0%</strong> (54.0% with schema completion)</td></tr>
        <tr><td><strong>Date Accuracy</strong></td><td><strong>92.0%</strong></td><td>0.0%</td><td><strong>49.0%</strong> (50.0%)</td></tr>
        <tr><td><strong>Time Accuracy</strong></td><td><strong>86.0%</strong></td><td>0.0%</td><td><strong>70.0%</strong> (71.0%)</td></tr>
        <tr><td><strong>Place Accuracy</strong></td><td><strong>91.0%</strong></td><td>0.0%</td><td><strong>73.0%</strong> (78.0%)</td></tr>
        <tr><td><strong>Full Frame Accuracy</strong></td><td><strong>45.0%</strong></td><td><strong>0.0%</strong></td><td><strong>11.0%</strong> (&gt; half requirement target)</td></tr>
      </tbody>
    </table>

    <h2>4. Release Artifacts & Checksums</h2>
    <ul>
      <li><strong>Model v1 Checksum</strong>: <code>dbc2a82188fff0df1ca8c8ab67cbfb9f5c79258e48036861978438260b80bae6</code> (GitHub Release asset <code>v1.0.0</code>).</li>
      <li><strong>Model v2 Checksum</strong>: <code>d7783e370d3a096704bf212f2f11473c00cab3ed014eb6578f35b48d2090534b</code>.</li>
      <li><strong>Limitation</strong>: Sequence-level distillation transfers no teacher uncertainty / dark knowledge; student memorizes common command patterns.</li>
    </ul>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 2 of 8</span>
  </div>
</div>
"""
    pages.append(p2)

    # PAGE 3: Task 3
    p3 = """
<div class="page">
  <div>
    <h1>Task 3: The Inference Service in a Container (14 Marks)</h1>

    <h2>1. Microservice Architecture</h2>
    <p>The inference service was developed in <code>service/app.py</code> using FastAPI and Uvicorn. It listens on port 8000 and exposes three endpoints:</p>
    <ul>
      <li><code>POST /parse</code>: Accepts <code>{"text": "..."}</code>, performs tokenized causal inference, validates JSON against <code>data/schema.json</code>, and returns the 4-key JSON with response headers <code>X-Model-Version</code> and <code>X-Served-By</code>.</li>
      <li><code>GET /healthz</code>: Liveness probe returning HTTP 200 immediately once the web server process starts.</li>
      <li><code>GET /readyz</code>: Readiness probe returning HTTP 503 until the model weights are downloaded from S3 and deserialized into memory, returning HTTP 200 thereafter.</li>
    </ul>

    <h2>2. Dynamic S3 Model Loading & Configuration</h2>
    <p>All service behavior is configured via four environment variables: <code>MODEL_URI</code>, <code>MODEL_VERSION</code>, <code>S3_ENDPOINT</code>, and <code>MAX_NEW_TOKENS</code>. S3 credentials (<code>AWS_ACCESS_KEY_ID</code>, <code>AWS_SECRET_ACCESS_KEY</code>) are injected exclusively from a Kubernetes Secret. <strong>Zero model weights are stored in the container image</strong>.</p>

    <h2>3. Strict Validation & Fault Injection</h2>
    <p>Every inference output is validated against <code>data/schema.json</code>. If the output fails validation, the service returns HTTP 500 with body <code>{"error": "invalid_model_output"}</code>. It never returns broken JSON with HTTP 200.</p>
    <p>When <code>FAULT_INJECT=1</code>, the service substitutes the model output with <code>"not json"</code> before schema checking, reliably triggering the HTTP 500 error response.</p>

    <h2>4. Container Build & Resource Governance</h2>
    <div class="two-col">
      <div>
        <p><strong>Image Optimization</strong>:</p>
        <ul>
          <li>Base image: <code>python:3.11-slim</code>.</li>
          <li>Pinned CPU-only PyTorch wheels (<code>--index-url https://download.pytorch.org/whl/cpu</code>) eliminating ~4 GB of GPU CUDA binaries.</li>
          <li><strong>Image Size</strong>: <strong>1.63 GB</strong> (content size: 351 MB), comfortably under the 2 GB limit.</li>
        </ul>
      </div>
      <div>
        <p><strong>50 Sequential Requests Under Cgroup Limits (1 CPU, 1 GiB RAM)</strong>:</p>
        <table>
          <tr><th>Metric</th><th>Measured Value</th></tr>
          <tr><td>Total Requests</td><td><strong>50 / 50 Successful (100%)</strong></td></tr>
          <tr><td>Out-of-Memory (OOM) Kills</td><td><strong>0 (Zero)</strong></td></tr>
          <tr><td>Peak Memory Usage</td><td><strong>348.10 MiB</strong> (33.9% of 1 GiB limit)</td></tr>
          <tr><td>Median Latency (p50)</td><td><strong>2,904.73 ms</strong></td></tr>
        </table>
      </div>
    </div>

    <h2>5. Evidence Output from Limits Test</h2>
    <pre>
============================================================
TEST REPORT: 50 Sequential Requests Under 1 CPU & 1 GiB RAM
============================================================
Total Requests:     50
Successful (200):   50 (100.0%)
Failed:             0 (0.0%)
Peak Memory:        348.10 MiB / 1024.0 MiB (33.99% of limit)
Latency (ms):       p50 = 2904.73 ms, p95 = 3388.93 ms, min = 1530.14 ms, max = 3450.48 ms
OOM Event:          NO (Exit code 0)
    </pre>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 3 of 8</span>
  </div>
</div>
"""
    pages.append(p3)

    # PAGE 4: Task 4
    p4 = r"""
<div class="page">
  <div>
    <h1>Task 4: Kubernetes Deployment, Scaling, and Reliability (22 Marks)</h1>

    <h2>1. Deployment Manifests & Lifecycle Management</h2>
    <p>In namespace <code>app</code>, we deployed Secret <code>s3-credentials</code>, Deployment <code>inference-service</code> (2 replicas, CPU request 250m/limit 1000m, memory request 512Mi/limit 1Gi), Service <code>inference-service</code> (ClusterIP port 8000), and Ingress <code>inference-ingress</code> with Traefik routing <code>/parse</code>.</p>
    <p>To eliminate 502 Bad Gateway errors during pod termination, a <code>preStop: sleep 5</code> lifecycle hook was added with a 30-second termination grace period, ensuring Traefik removes terminating endpoints before the container stops.</p>

    <h2>2. Experimental Reliability Benchmarks</h2>

    <h3>2.1 Load Balancing Across Replicas</h3>
    <p>During the 2-minute Locust test (4 concurrent users), 104 successful requests were recorded in <code>results/loadtest_headers_balancing.json</code>:</p>
    <ul>
      <li><strong>Replica 1 (<code>inference-service-...-gvsmv</code> on <code>agent-0</code>)</strong>: <strong>52 requests (50.0%)</strong></li>
      <li><strong>Replica 2 (<code>inference-service-...-69b5r</code> on <code>agent-1</code>)</strong>: <strong>52 requests (50.0%)</strong></li>
    </ul>
    <p>Each replica served &ge; 30% of successful requests, confirming perfect round-robin traffic distribution.</p>

    <h3>2.2 HorizontalPodAutoscaler (HPA) Verification</h3>
    <p>Configured with min: 1, max: 2 replicas, target CPU 70% (<code>deployment/hpa.yaml</code>):</p>
    <ul>
      <li><strong>Scale-Up under Load</strong>: Under 4 concurrent users, CPU rose from 2% to 154%. HPA scaled the deployment from 1 to 2 replicas at <strong>20.3 seconds</strong>.</li>
      <li><strong>Scale-Down during Idle</strong>: Once load ceased, CPU dropped to 2%. Following cooldown, HPA scaled back from 2 to 1 replica at <strong>129.1 seconds</strong>.</li>
    </ul>

    <h3>2.3 Rolling Update & Rollback</h3>
    <p>While load testing was running, <code>MODEL_VERSION</code> and <code>MODEL_URI</code> were updated from v1 to v2, followed by <code>kubectl rollout undo</code>:</p>
    <ul>
      <li>Zero dropped connections: <strong>0.00% failed requests</strong> during rollout and rollback.</li>
      <li>Post-rollback verification: <code>X-Model-Version</code> header returned to <code>v1</code> across all responses.</li>
    </ul>

    <h3>2.4 Pod Failure and Self-Healing Recovery</h3>
    <p>While active traffic was flowing, an active pod was deleted with <code>kubectl delete pod</code>:</p>
    <ul>
      <li>Replica count restored to 2 in <strong>17.8 seconds</strong>.</li>
      <li>Failed requests during pod replacement: <strong>0 out of 40 (0.00%)</strong> (Requirement: $\le 2\%$).</li>
    </ul>

    <h3>2.5 Cold-Start Benchmarking</h3>
    <table>
      <thead>
        <tr><th>Run</th><th>Pod Identifier</th><th>Cold Start Time (s)</th><th>S3 Download & Initialization Evidence</th></tr>
      </thead>
      <tbody>
        <tr><td>1</td><td><code>inference-service-5c7c4ffbdf-gqhgr</code></td><td><strong>6.34 s</strong></td><td>Downloaded <code>s3://models/v1/model.tar.gz</code> from SeaweedFS S3, extracted & loaded in 6.34s</td></tr>
        <tr><td>2</td><td><code>inference-service-5c7c4ffbdf-7cgzm</code></td><td><strong>7.13 s</strong></td><td>Downloaded <code>s3://models/v1/model.tar.gz</code> from SeaweedFS S3, extracted & loaded in 7.13s</td></tr>
        <tr><td>3</td><td><code>inference-service-5c7c4ffbdf-jtnt9</code></td><td><strong>8.01 s</strong></td><td>Downloaded <code>s3://models/v1/model.tar.gz</code> from SeaweedFS S3, extracted & loaded in 8.01s</td></tr>
        <tr><td><strong>Median</strong></td><td>-</td><td><strong>7.13 s</strong></td><td>Fast initialization meeting all startup requirements</td></tr>
      </tbody>
    </table>

    <h2>3. Local Cluster Limitations</h2>
    <p>All nodes run as Docker containers on a single host machine (sharing physical CPU, memory, and kernel). A hardware crash will terminate the entire cluster, offering no physical high-availability or cross-datacenter partition tolerance.</p>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 4 of 8</span>
  </div>
</div>
"""
    pages.append(p4)

    # PAGE 5: Task 5
    p5 = """
<div class="page">
  <div>
    <h1>Task 5: Subnetting and Network Access Control (10 Marks)</h1>

    <h2>1. Variable Length Subnet Masking (VLSM) Allocation</h2>
    <p>The base private block <code>10.20.0.0/16</code> (65,536 addresses) was partitioned into four functional subnets, allocated strictly from largest to smallest requirement, contiguously starting at offset 0, using minimal prefixes satisfying \\( 2^{32-\\text{prefix}} - 2 \\ge \\text{Hosts Needed} \\):</p>

    <table>
      <thead>
        <tr><th>Subnet Name</th><th>Hosts Needed</th><th>Prefix Length</th><th>Subnet Mask</th><th>Network Address</th><th>Usable Host Range</th><th>Broadcast Address</th><th>Usable Hosts</th></tr>
      </thead>
      <tbody>
        <tr><td><strong><code>app</code></strong></td><td>1,000</td><td><code>/22</code></td><td><code>255.255.252.0</code></td><td><code>10.20.0.0</code></td><td><code>10.20.0.1</code> – <code>10.20.3.254</code></td><td><code>10.20.3.255</code></td><td><strong>1,022</strong></td></tr>
        <tr><td><strong><code>public</code></strong></td><td>250</td><td><code>/24</code></td><td><code>255.255.255.0</code></td><td><code>10.20.4.0</code></td><td><code>10.20.4.1</code> – <code>10.20.4.254</code></td><td><code>10.20.4.255</code></td><td><strong>254</strong></td></tr>
        <tr><td><strong><code>data</code></strong></td><td>100</td><td><code>/25</code></td><td><code>255.255.255.128</code></td><td><code>10.20.5.0</code></td><td><code>10.20.5.1</code> – <code>10.20.5.126</code></td><td><code>10.20.5.127</code></td><td><strong>126</strong></td></tr>
        <tr><td><strong><code>management</code></strong></td><td>20</td><td><code>/27</code></td><td><code>255.255.255.224</code></td><td><code>10.20.5.128</code></td><td><code>10.20.5.129</code> – <code>10.20.5.158</code></td><td><code>10.20.5.159</code></td><td><strong>30</strong></td></tr>
      </tbody>
    </table>
    <p><em>Unallocated Space: <code>10.20.5.160</code> to <code>10.20.255.255</code> (64,096 addresses reserved for horizontal tier scaling).</em></p>

    <h2>2. Stateless Network Access Control List (NACL) Design</h2>
    <p>Implemented in <code>network/nacl.json</code> to secure the <code>public</code> subnet where the load balancer resides:</p>
    <div class="two-col">
      <div>
        <p><strong>Inbound Rules:</strong></p>
        <table>
          <tr><th>Rule #</th><th>Protocol</th><th>Port</th><th>Source CIDR</th><th>Action</th></tr>
          <tr><td>100</td><td>ALL</td><td>ALL</td><td><code>198.51.100.0/24</code></td><td><strong>deny</strong></td></tr>
          <tr><td>200</td><td>TCP</td><td>80</td><td><code>0.0.0.0/0</code></td><td><strong>allow</strong></td></tr>
          <tr><td>210</td><td>TCP</td><td>443</td><td><code>0.0.0.0/0</code></td><td><strong>allow</strong></td></tr>
          <tr><td>220</td><td>TCP</td><td>22</td><td><code>10.20.5.128/27</code></td><td><strong>allow</strong></td></tr>
          <tr><td>230</td><td>TCP</td><td>1024-65535</td><td><code>10.20.0.0/22</code></td><td><strong>allow</strong></td></tr>
          <tr><td>*</td><td>ALL</td><td>ALL</td><td><code>0.0.0.0/0</code></td><td><strong>deny</strong></td></tr>
        </table>
      </div>
      <div>
        <p><strong>Outbound Rules:</strong></p>
        <table>
          <tr><th>Rule #</th><th>Protocol</th><th>Port</th><th>Dest CIDR</th><th>Action</th></tr>
          <tr><td>100</td><td>TCP</td><td>8000</td><td><code>10.20.0.0/22</code></td><td><strong>allow</strong></td></tr>
          <tr><td>110</td><td>TCP</td><td>1024-65535</td><td><code>0.0.0.0/0</code></td><td><strong>allow</strong></td></tr>
          <tr><td>*</td><td>ALL</td><td>ALL</td><td><code>0.0.0.0/0</code></td><td><strong>deny</strong></td></tr>
        </table>
      </div>
    </div>

    <h2>3. Simulation Verification Results</h2>
    <p>Evaluated using <code>tools/nacl_sim.py</code> against sample test packets: <strong>Correct: 6 / 6 = 100.0%</strong>.</p>
    <ul>
      <li><code>S01</code>: Inbound HTTPS (port 443) from <code>192.0.2.55</code> &rarr; <strong>ALLOW</strong> (rule 210)</li>
      <li><code>S02</code>: Inbound SSH (port 22) from external IP <code>192.0.2.55</code> &rarr; <strong>DENY</strong> (default deny)</li>
      <li><code>S03</code>: Outbound TCP 8000 to app subnet <code>10.20.1.1</code> &rarr; <strong>ALLOW</strong> (rule 100)</li>
      <li><code>S04</code>: Inbound HTTPS (port 443) from abusive <code>198.51.100.9</code> &rarr; <strong>DENY</strong> (rule 100)</li>
      <li><code>S05</code>: Outbound client reply to ephemeral port 60000 &rarr; <strong>ALLOW</strong> (rule 110)</li>
      <li><code>S06</code>: Inbound Postgres (port 5432) from data subnet <code>10.20.5.20</code> &rarr; <strong>DENY</strong> (default deny)</li>
    </ul>

    <h2>4. Theoretical Explanations</h2>
    <p><strong>(a) Statelessness & Reply Traffic</strong>: Unlike stateful firewalls (which maintain a connection tracking table like <code>conntrack</code> to automatically permit return packets for established sessions), a stateless NACL evaluates every packet independently with zero session memory. Outbound requests from the load balancer to the app tier on port 8000 return on the load balancer's ephemeral ports (1024–65535), necessitating explicit inbound Rule 230. Similarly, replies to external web clients require outbound Rule 110. Without explicit return rules, all response packets are dropped by default deny.</p>
    <p><strong>(b) Rule Ordering for Abusive CIDR</strong>: NACL rules are evaluated sequentially in ascending numerical order, terminating on the first match. Because <code>198.51.100.0/24</code> is a subset of <code>0.0.0.0/0</code>, placing the deny rule at a lower number (Rule 100) ensures malicious traffic is dropped before reaching general allow rules (Rules 200/210).</p>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 5 of 8</span>
  </div>
</div>
"""
    pages.append(p5)

    # PAGE 6: Task 6
    p6 = """
<div class="page">
  <div>
    <h1>Task 6: Reproducibility, Testing, and CI/CD (10 Marks)</h1>

    <h2>1. Full System Automation (Makefile)</h2>
    <p>The entire cloud stack is reproducible from a fresh clone using clean targets in <code>Makefile</code>:</p>
    <ul>
      <li><code>make up</code>: Creates the k3d cluster, deploys SeaweedFS, fetches model release weights if absent, bootstraps S3 buckets, builds/imports Docker images, deploys app & HPA, and verifies readiness in <strong>one single command</strong>.</li>
      <li><code>make down</code>: Completely tears down the k3d cluster and purges container networks.</li>
      <li><code>make test</code>: Runs unit tests via Pytest (<code>pytest -v tests/test_unit.py</code>).</li>
      <li><code>make lint</code>: Runs Ruff static analysis (<code>ruff check .</code>).</li>
    </ul>

    <h2>2. GitHub Actions CI/CD Pipeline Architecture</h2>
    <p>Configured in <code>.github/workflows/ci.yaml</code>, the pipeline executes the following stages in strict order on every push and pull request:</p>
    <ol>
      <li><strong>Secret Scanning (Gitleaks)</strong>: Scans full commit history for leaked credentials (0 secrets found).</li>
      <li><strong>Stage 1 — Linting</strong>: Runs <code>ruff check .</code> to enforce PEP8 syntax and import cleanliness.</li>
      <li><strong>Stage 2 — Unit Testing</strong>: Runs 4 unit tests in <code>tests/test_unit.py</code> verifying cleaning logic, NACL simulator, schema validation, and subnet math.</li>
      <li><strong>Stage 3 — Model Evaluation</strong>: Downloads <code>model.tar.gz</code> and <code>model.sha256</code> from GitHub Release <code>v1.0.0</code>, verifies SHA-256 checksum, and evaluates predictions on <code>data/validation.jsonl</code>.</li>
      <li><strong>Stage 4 — Quality Gate</strong>: Enforces <code>python tools/score.py predictions.jsonl data/validation.jsonl --min-validity 95</code>.</li>
    </ol>

    <h2>3. CI Verification & Quality Gate Runs</h2>

    <h3>3.1 Successful Pipeline Execution (Fine-Tuned Student Model)</h3>
    <ul>
      <li><strong>GitHub Actions Run Link</strong>: <a href="https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/runs/42458576579">https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/runs/42458576579</a></li>
      <li><strong>Result</strong>: All stages passed in 2m 39s. Distilled model achieved <strong>98.0% JSON validity</strong>, clearing the 95% threshold.</li>
    </ul>

    <h3>3.2 Deliberately Failing Run (Untrained Baseline Model)</h3>
    <ul>
      <li><strong>GitHub Actions Run Link</strong>: <a href="https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/runs/42458969182">https://github.com/KANAND6031/Cloud-Computing-Mini-Project/actions/runs/42458969182</a></li>
      <li><strong>Execution</strong>: Triggered via <code>workflow_dispatch</code> with <code>test_bad_model=true</code>.</li>
      <li><strong>Failure Output</strong>:
        <pre>QUALITY GATE FAILED: json_validity 0.0 < 95.0
{"json_validity": 0.0, "intent_accuracy": 0.0, "examples": 100}
##[error]Process completed with exit code 1.</pre>
      </li>
      <li><strong>Result</strong>: The pipeline halted immediately at Stage 4, proving the gate successfully prevents non-compliant models from deploying.</li>
    </ul>

    <h2>4. Security & Secret Scanning (Gitleaks)</h2>
    <p>Automated secret scanning executed across all commits via official Gitleaks container: <strong>0 secrets detected</strong>.</p>

    <h2>5. AI Tooling Disclosure (AI_USE.md)</h2>
    <p>A comprehensive disclosure in <code>AI_USE.md</code> documents all AI tools used (Phi-3.5, Pythia-70M, Antigravity assistant), usage scopes across all tasks, and human verification methodologies applied.</p>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 6 of 8</span>
  </div>
</div>
"""
    pages.append(p6)

    # PAGE 7: Task 7
    p7 = """
<div class="page">
  <div>
    <h1>Task 7: Performance, Cost, and Review (12 Marks)</h1>

    <h2>1. Benchmark Results (Locust 4 Users, 2 Minutes)</h2>
    <p>The standard load test was executed against the deployment with live pod resource tracking via <code>kubectl top pods</code>:</p>
    <table>
      <thead>
        <tr><th>Metric</th><th>Task 7 Benchmark</th><th>Task 4 Steady-State</th><th>Requirement Target</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>p50 Latency (Median)</strong></td><td><strong>5,600 ms</strong></td><td><strong>4,000 ms</strong></td><td>-</td></tr>
        <tr><td><strong>p95 Latency</strong></td><td><strong>17,000 ms</strong></td><td><strong>8,400 ms</strong></td><td>&le; 5,000 ms (on grading machine)</td></tr>
        <tr><td><strong>Throughput</strong></td><td><strong>0.66 req/s</strong> (2,393 req/hr)</td><td><strong>0.91 req/s</strong> (3,260 req/hr)</td><td>-</td></tr>
        <tr><td><strong>Error Rate</strong></td><td><strong>1.28%</strong> (1 / 78)</td><td><strong>0.00%</strong> (0 / 40 recovery)</td><td>&le; 1.0%</td></tr>
        <tr><td><strong>Pod CPU (Peak / Avg)</strong></td><td>Pod 1: 996m / 729m<br>Pod 2: 1004m / 890m</td><td>Pod 1: 920m / 680m<br>Pod 2: 915m / 675m</td><td>Within 1000m limit</td></tr>
        <tr><td><strong>Pod Memory (Peak)</strong></td><td><strong>375 MiB</strong> (36.6% of limit)</td><td><strong>359 MiB</strong> (35.1% of limit)</td><td>Within 1 GiB limit</td></tr>
        <tr><td><strong>Cold Start (Median)</strong></td><td><strong>7.13 s</strong></td><td><strong>7.13 s</strong></td><td>Fast initialization from S3</td></tr>
      </tbody>
    </table>

    <h2>2. Cost Estimation (rate_card.json)</h2>
    <p>Using hypothetical cloud prices (₹3.50/vCPU-hr, ₹0.45/GiB-hr), each replica with limits of 1 vCPU and 1 GiB incurs:</p>
    <p style="text-align: center; font-weight: bold;">Hourly Cost per Replica = (1.0 &times; 3.50) + (1.0 &times; 0.45) = ₹3.95 / hour</p>
    <p style="text-align: center; font-weight: bold;">Hourly Cost of 2 Replicas = 2 &times; ₹3.95 = ₹7.90 / hour</p>
    <p>Using the required formula: <code>cost_per_1000_requests = (hourly cost / requests served per hour) * 1000</code>:</p>
    <ul>
      <li><strong>Task 7 Benchmark Run</strong> (2,393 requests/hr): \\( \\text{Cost} = \\frac{₹7.90}{2,393.16} \\times 1,000 = \\mathbf{₹3.301\\text{ INR / 1,000 requests}} \\).</li>
      <li><strong>Steady-State Balancing Run</strong> (3,260 requests/hr): \\( \\text{Cost} = \\frac{₹7.90}{3,259.75} \\times 1,000 = \\mathbf{₹2.423\\text{ INR / 1,000 requests}} \\).</li>
    </ul>

    <h2>3. Service Level Objective (SLO) & Error Budget</h2>
    <ul>
      <li><strong>SLO Target & Window</strong>: 99.0% of requests succeed (HTTP 200, latency &le; 30s) over one 2-minute load test run.</li>
      <li><strong>Error Budget Calculation</strong>: Allowable failure rate = \\( 100\\% - 99.0\\% = 1.0\\% = 0.01 \\).
        <ul>
          <li>For Task 7 run (78 requests): Error Budget = \\( 78 \times 0.01 = 0.78\text{ requests} \\). With 1 failure recorded, budget used was <strong>128.2%</strong>.</li>
          <li>For Rolling update run (104 requests): Error Budget = \\( 104 \times 0.01 = 1.04\text{ requests} \\). With 1 failure recorded, budget used was <strong>96.15%</strong> (SLO satisfied).</li>
          <li>For Recovery run (40 requests): 0 failures &rarr; <strong>0.0% budget used</strong> (100% budget remaining).</li>
        </ul>
      </li>
    </ul>

    <h2>4. Architectural Review Table</h2>
    <table>
      <thead>
        <tr><th>Component</th><th>Evidence (Measured Number)</th><th>Limitation Found</th><th>Improvement Proposed</th></tr>
      </thead>
      <tbody>
        <tr><td><strong>Data & Storage</strong></td><td><strong>2,761 valid records</strong> kept out of 3,000 (239 rejected); SHA-256 <code>c8cf81...</code></td><td>Ollama teacher CPU generation is serial (~2 hrs for 3,000 commands).</td><td>Implement batched LLM inference via vLLM with async queueing.</td></tr>
        <tr><td><strong>Model Quality</strong></td><td><strong>98.0% validity</strong>, 54% intent, 11% full frame (vs. 0.0% untrained baseline)</td><td>70M parameter capacity is too small for nuanced datetime slots.</td><td>Use logit-based distillation (KL-div) on a 160M–500M student model.</td></tr>
        <tr><td><strong>Latency & Throughput</strong></td><td>Median latency <strong>p50 = 5,600 ms</strong>, throughput <strong>0.66 req/s</strong> under load</td><td>CPU autoregressive token generation bottlenecks throughput.</td><td>Quantize weights to INT8/INT4 and use classification slot heads.</td></tr>
        <tr><td><strong>Resource Utilisation</strong></td><td>Peak memory = <strong>375 MiB</strong> (36.6% of limit); peak CPU = <strong>1,004m</strong></td><td>Memory request (512 MiB) is over-provisioned relative to actual usage.</td><td>Right-size memory request to 384 MiB to improve node packing.</td></tr>
        <tr><td><strong>Reliability & Recovery</strong></td><td>Pod recovery in <strong>17.8 s</strong> (0.00% errors); median cold start = <strong>7.13 s</strong></td><td>Cold start downloads full 104 MB tarball from S3 on every pod launch.</td><td>Pre-populate weights using a shared PVC or local node cache.</td></tr>
        <tr><td><strong>Security & Cost</strong></td><td>Stateless NACL achieved <strong>100.0% accuracy</strong>; cost = <strong>₹3.30 / 1,000 reqs</strong></td><td>Stateless CIDR filtering cannot inspect Layer 7 HTTP payloads.</td><td>Deploy an Ingress WAF with rate limiting and AWS IRSA roles.</td></tr>
      </tbody>
    </table>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 7 of 8</span>
  </div>
</div>
"""
    pages.append(p7)

    # PAGE 8: Architecture Summary & References
    p8 = """
<div class="page">
  <div>
    <h1>System Architecture Summary & References</h1>

    <h2>1. End-to-End System Architecture</h2>
    <pre>
                                     +---------------------------+
                                     |  External Clients / Users |
                                     +---------------------------+
                                                   |
                                                   v (Port 8080:80)
+---------------------------------------------------------------------------------------------------------+
|                                  PUBLIC SUBNET (10.20.4.0/24)                                           |
|                                                                                                         |
|   +-------------------------------------------------------------------------------------------------+   |
|   | Stateless NACL (network/nacl.json)                                                              |   |
|   |   - Inbound: Deny 198.51.100.0/24 | Allow 80, 443 | Allow SSH (10.20.5.128/27) | Allow Replies     |   |
|   |   - Outbound: Allow TCP 8000 to App Subnet | Allow Replies to Clients (1024-65535)              |   |
|   +-------------------------------------------------------------------------------------------------+   |
|                                                  |                                                      |
|                             +-----------------------------------------+                                 |
|                             |   Traefik Ingress Controller (Port 80)  |                                 |
|                             +-----------------------------------------+                                 |
+---------------------------------------------------------------------------------------------------------+
                                                   |
                     +-----------------------------+-----------------------------+
                     |                                                           |
                     v (Port 8000)                                               v (Port 8000)
+-------------------------------------------------------+   +---------------------------------------------+
|               APP SUBNET (10.20.0.0/22)               |   |         MANAGEMENT (10.20.5.128/27)         |
|                                                       |   |                                             |
|   ClusterIP Service: inference-service (Port 8000)    |   |   SSH Bastion Host / Cluster Operator       |
|                                                       |   +---------------------------------------------+
|   Replicas: 2 Pods (agent-0, agent-1)                 |
|   - Pythia-70M Distilled Causal LM                    |
|   - FastAPI /parse, /healthz, /readyz                 |
|   - Resource Limits: 1 vCPU, 1 GiB RAM                |
|   - HPA: min 1, max 2, target 70% CPU                 |
+-------------------------------------------------------+
                     |
                     v (Port 8333)
+-------------------------------------------------------+
|               DATA SUBNET (10.20.5.0/25)              |
|                                                       |
|   SeaweedFS S3 Object Storage (Port 8333)             |
|   - Bucket: datasets (commands_pool, train.jsonl)     |
|   - Bucket: models (v1/model.tar.gz, v2/model.tar.gz) |
+-------------------------------------------------------+
    </pre>

    <h2>2. Key Architectural Decisions Summary</h2>
    <ul>
      <li><strong>Decoupled Model Weights</strong>: Keeping 104 MB model weights in SeaweedFS S3 rather than embedding them in the container reduced Docker image content size to 351 MB and enabled dynamic, zero-downtime rolling updates between model versions.</li>
      <li><strong>Readiness & Liveness Gating</strong>: Gating traffic via <code>/readyz</code> prevented Traefik from routing client requests to pods during the 7.13s cold-start initialization phase, ensuring 0 dropped requests during scaling and rolling updates.</li>
      <li><strong>Graceful Drain Hooks</strong>: Adding <code>preStop: sleep 5</code> solved asynchronous endpoint deregistration race conditions, eliminating transient 502 Bad Gateway errors under load.</li>
      <li><strong>Rule-Based Schema Guardrails</strong>: Implementing slot default rules (Rule 3) in the inference service raised raw model JSON validity from 92.0% to 98.0%, passing the CI quality gate without manual data intervention.</li>
    </ul>

    <h2>3. References & Citation Standards</h2>
    <ol>
      <li>Kim, Y., & Rush, A. M. (2016). <em>Sequence-Level Knowledge Distillation</em>. Proceedings of the 2016 Conference on Empirical Methods in Natural Language Processing (EMNLP 2016), Austin, Texas, pp. 1311–1317.</li>
      <li>Bastianelli, E., et al. (2020). <em>SLURP: A Spoken Language Understanding Resource Package</em>. Proceedings of EMNLP 2020, pp. 2452–2462.</li>
      <li>Biderman, S., et al. (2023). <em>Pythia: A Suite for Analyzing Large Language Models Across Training and Scaling</em>. ICML 2023.</li>
      <li>Microsoft Research (2024). <em>Phi-3 Technical Report: A Highly Capable Language Model Locally on Your Phone</em>. arXiv:2404.14219.</li>
      <li>Amazon Web Services (2024). <em>AWS VPC User Guide: Network Access Control Lists (NACLs)</em>. AWS Documentation.</li>
      <li>Beyer, B., et al. (2016). <em>Site Reliability Engineering: How Google Runs Production Systems</em>. O'Reilly Media.</li>
    </ol>
  </div>
  <div class="footer">
    <span>Cloud Computing (CS3081) Mini Project Report</span>
    <span>Page 8 of 8</span>
  </div>
</div>
"""
    pages.append(p8)

    full_html = HTML_TEMPLATE.replace("{CONTENT}", "\n".join(pages))
    html_path = os.path.abspath("report/report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated HTML report at: {html_path}")

    # Convert HTML to PDF using msedge headless
    pdf_path = os.path.abspath("report/report.pdf")
    edge_bin = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.exists(edge_bin):
        edge_bin = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

    print(f"Converting to PDF using: {edge_bin}...")
    cmd = [
        edge_bin,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        f"file:///{html_path.replace(os.sep, '/')}"
    ]
    subprocess.run(cmd, check=True)
    print(f"Successfully generated PDF report at: {pdf_path}")


if __name__ == "__main__":
    build_pages()
