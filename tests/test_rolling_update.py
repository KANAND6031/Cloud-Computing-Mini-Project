import os
import time
import json
import subprocess

OUT_FILE = "results/rolling_update_test.json"
HEADERS_FILE = "results/loadtest_headers_rolling.json"
STATS_FILE = "results/loadtest_stats_rolling.csv"


def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()


def main():
    print("=" * 60)
    print("Task 4: Rolling Update (v1 -> v2 -> rollback to v1) Under Load")
    print("=" * 60)

    # 1. Set deployment replicas to 2 and ensure both are Ready
    run_cmd("kubectl scale deployment/inference-service -n app --replicas=2")
    run_cmd("kubectl wait --for=condition=ready pod -l app=inference-service -n app --timeout=60s")
    print("Replicas ready. Starting Locust load test (4 users, 130s)...")

    # Set env var for Locust headers output
    env = os.environ.copy()
    env["LOADTEST_HEADERS_OUT"] = HEADERS_FILE
    env["LOADTEST_TEXTS"] = "data/loadtest_valid.jsonl"

    locust_proc = subprocess.Popen(
        [r".\.venv\Scripts\locust.exe", "-f", "tools/locustfile.py", "--headless",
         "--users", "4", "--spawn-rate", "4", "--run-time", "130s",
         "--host", "http://localhost:8080", "--csv", "results/loadtest_rolling"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    t0 = time.time()
    # Let steady state run for 15s
    print("1. Running on v1 for 15s...")
    time.sleep(15)

    # Trigger rolling update to v2
    print("\n2. Updating to MODEL_VERSION=v2 and MODEL_URI=s3://models/v2/model.tar.gz...")
    t_v2_start = time.time() - t0
    run_cmd("kubectl set env deployment/inference-service -n app MODEL_VERSION=v2 MODEL_URI=s3://models/v2/model.tar.gz")

    print("Waiting for v2 rollout to complete...")
    v2_status = run_cmd("kubectl rollout status deployment/inference-service -n app --timeout=60s")
    t_v2_done = time.time() - t0
    print(f"v2 rollout status: {v2_status} (completed at {t_v2_done:.1f}s)")

    # Run on v2 for 15s
    print("Serving on v2 for 15s...")
    time.sleep(15)

    # Trigger rollback to v1
    print("\n3. Triggering rollback: kubectl rollout undo deployment/inference-service -n app...")
    t_undo_start = time.time() - t0
    run_cmd("kubectl rollout undo deployment/inference-service -n app")

    print("Waiting for rollback to complete...")
    undo_status = run_cmd("kubectl rollout status deployment/inference-service -n app --timeout=60s")
    t_undo_done = time.time() - t0
    print(f"Rollback status: {undo_status} (completed at {t_undo_done:.1f}s)")

    # Wait for Locust to finish
    print("\n4. Waiting for Locust load test to finish...")
    locust_proc.wait()
    print("Locust completed.")

    # Check current deployment env after rollback
    dep_json = json.loads(run_cmd("kubectl get deployment inference-service -n app -o json"))
    env_vars = {e["name"]: e.get("value", "") for e in dep_json["spec"]["template"]["spec"]["containers"][0]["env"]}
    active_version_after_rollback = env_vars.get("MODEL_VERSION", "")

    # Parse headers results
    headers_data = {}
    if os.path.exists(HEADERS_FILE):
        with open(HEADERS_FILE, "r", encoding="utf-8") as f:
            headers_data = json.load(f)

    # Parse CSV stats
    stats_csv_path = "results/loadtest_rolling_stats.csv"
    total_reqs = 0
    failures = 0
    if os.path.exists(stats_csv_path):
        import csv
        with open(stats_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Name") == "Aggregated":
                    total_reqs = int(row.get("Request Count", 0))
                    failures = int(row.get("Failure Count", 0))

    # Note: Locust failures can include 500s from schema validation rejections
    # To determine actual network/drop failures vs schema validation rejections:
    # Check pod logs for 500 rejections
    fail_rate = (failures / total_reqs * 100.0) if total_reqs > 0 else 0.0

    summary = {
        "total_requests": total_reqs,
        "total_failures": failures,
        "failure_rate_percent": round(fail_rate, 2),
        "v2_rollout_status": v2_status,
        "rollback_status": undo_status,
        "active_model_version_after_rollback": active_version_after_rollback,
        "served_by_headers": headers_data,
        "timestamps": {
            "v2_update_triggered": round(t_v2_start, 1),
            "v2_rollout_completed": round(t_v2_done, 1),
            "undo_triggered": round(t_undo_start, 1),
            "undo_completed": round(t_undo_done, 1)
        }
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("ROLLING UPDATE TEST SUMMARY")
    print("=" * 60)
    print(f"Total Requests: {total_reqs}")
    print(f"Total Failures: {failures} ({fail_rate:.2f}%)")
    print(f"Active MODEL_VERSION after rollback: {active_version_after_rollback}")
    print(f"Headers Breakdown: {json.dumps(headers_data, indent=2)}")
    print(f"Report written to {OUT_FILE}")


if __name__ == "__main__":
    main()
