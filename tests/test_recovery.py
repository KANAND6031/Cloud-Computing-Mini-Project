import os
import sys
import time
import json
import csv
import subprocess

OUT_FILE = "results/recovery_test.json"
HEADERS_FILE = "results/loadtest_headers_recovery.json"
STATS_CSV = "results/loadtest_recovery_stats.csv"
FAILURES_CSV = "results/loadtest_recovery_failures.csv"


def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()


def get_ready_pods():
    out = run_cmd("kubectl get pods -n app -l app=inference-service --no-headers")
    lines = [l for l in out.splitlines() if l.strip()]
    ready_pods = []
    for l in lines:
        parts = l.split()
        if len(parts) >= 3:
            name = parts[0]
            ready_str = parts[1]
            status = parts[2]
            ready_pods.append({"name": name, "ready": ready_str, "status": status, "raw": l})
    return ready_pods


def main():
    print("=" * 60)
    print("Task 4: Pod Failure Recovery Under Load")
    print("=" * 60)

    # 1. Ensure deployment has 2 ready replicas
    run_cmd("kubectl scale deployment/inference-service -n app --replicas=2")
    run_cmd("kubectl wait --for=condition=ready pod -l app=inference-service -n app --timeout=60s")

    initial_pods = get_ready_pods()
    print(f"Initial Ready Pods ({len(initial_pods)}):")
    for p in initial_pods:
        print(f"  {p['raw']}")

    if len(initial_pods) < 2:
        sys.exit("Error: Expected at least 2 ready pods before starting test.")

    pod_to_delete = initial_pods[0]["name"]
    print(f"\nTarget pod for deletion: {pod_to_delete}")

    # 2. Launch Locust load test in background (4 users, 60s)
    print("\nStarting Locust load test (4 users, 60s)...")
    env = os.environ.copy()
    env["LOADTEST_HEADERS_OUT"] = HEADERS_FILE
    env["LOADTEST_TEXTS"] = "data/loadtest_valid.jsonl"

    locust_proc = subprocess.Popen(
        [r".\.venv\Scripts\locust.exe", "-f", "tools/locustfile.py", "--headless",
         "--users", "4", "--spawn-rate", "4", "--run-time", "60s",
         "--host", "http://localhost:8080", "--csv", "results/loadtest_recovery"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    t0 = time.time()
    # Let traffic run for 10s
    print("Traffic running for 10s before pod failure...")
    time.sleep(10)

    # 3. Delete the pod
    print(f"\n--> Deleting pod: {pod_to_delete}...")
    t_del_start = time.time() - t0
    run_cmd(f"kubectl delete pod {pod_to_delete} -n app --wait=false")

    # 4. Monitor restoration
    print("Monitoring replica restoration...")
    restored = False
    new_pod_name = None
    t_restored = None

    for _ in range(40):
        time.sleep(1)
        current_pods = get_ready_pods()
        ready_count = sum(1 for p in current_pods if p["ready"] == "1/1" and p["status"] == "Running")
        # Check if new pod appears
        for p in current_pods:
            if p["name"] != pod_to_delete and p["name"] not in [ip["name"] for ip in initial_pods]:
                new_pod_name = p["name"]

        if ready_count >= 2 and new_pod_name:
            restored = True
            t_restored = round(time.time() - t0, 1)
            print(f"--> Replica count restored to 2 at {t_restored}s! New pod: {new_pod_name}")
            break

    # 5. Wait for Locust to finish
    print("\nWaiting for Locust to conclude...")
    locust_proc.wait()
    print("Locust load test finished.")

    # 6. Parse results
    total_reqs = 0
    failures = 0
    if os.path.exists(STATS_CSV):
        with open(STATS_CSV, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Name") == "Aggregated":
                    total_reqs = int(row.get("Request Count", 0))
                    failures = int(row.get("Failure Count", 0))

    fail_rate = (failures / total_reqs * 100.0) if total_reqs > 0 else 0.0

    headers_data = {}
    if os.path.exists(HEADERS_FILE):
        with open(HEADERS_FILE, "r", encoding="utf-8") as f:
            headers_data = json.load(f)

    summary = {
        "pod_deleted": pod_to_delete,
        "deletion_time_sec": round(t_del_start, 1),
        "replica_count_restored": restored,
        "restoration_time_sec": t_restored,
        "new_pod_name": new_pod_name,
        "total_requests": total_reqs,
        "total_failures": failures,
        "failure_rate_percent": round(fail_rate, 2),
        "served_by_headers": headers_data
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("RECOVERY TEST SUMMARY")
    print("=" * 60)
    print(f"Pod Deleted: {pod_to_delete}")
    print(f"Replica Count Restored: {restored} (new pod {new_pod_name} Ready at {t_restored}s)")
    print(f"Total Requests: {total_reqs}")
    print(f"Failed Requests: {failures} ({fail_rate:.2f}%)")
    print(f"Headers Breakdown: {json.dumps(headers_data, indent=2)}")
    print(f"Report written to {OUT_FILE}")


if __name__ == "__main__":
    main()
