import time
import json
import statistics
import subprocess

OUT_FILE = "results/cold_start_test.json"


def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()


def run_single_cold_start(run_idx):
    print(f"\n--- Run {run_idx}/3 ---")
    # Scale to 0 to terminate existing pods
    print("Scaling deployment to 0 replicas...")
    run_cmd("kubectl scale deployment/inference-service -n app --replicas=0")
    # Wait until all pods are gone
    for _ in range(30):
        pods = run_cmd("kubectl get pods -n app -l app=inference-service --no-headers")
        if not pods.strip():
            break
        time.sleep(1)

    print("Scaling deployment to 1 replica to initiate fresh cold start...")
    t_start = time.time()
    run_cmd("kubectl scale deployment/inference-service -n app --replicas=1")

    pod_name = None
    # Wait for pod creation
    for _ in range(20):
        out = run_cmd("kubectl get pods -n app -l app=inference-service -o jsonpath='{.items[0].metadata.name}'").strip("'\"")
        if out and out != "":
            pod_name = out
            break
        time.sleep(0.5)

    if not pod_name:
        raise RuntimeError(f"Run {run_idx}: Pod was not created in time.")

    print(f"Pod created: {pod_name}. Monitoring time to Ready...")
    ready_time = None
    for _ in range(60):
        pod_json_str = run_cmd(f"kubectl get pod {pod_name} -n app -o json")
        try:
            pod_json = json.loads(pod_json_str)
            conditions = pod_json.get("status", {}).get("conditions", [])
            for c in conditions:
                if c.get("type") == "Ready" and c.get("status") == "True":
                    ready_time = time.time() - t_start
                    break
        except Exception:
            pass
        if ready_time is not None:
            break
        time.sleep(0.5)

    if ready_time is None:
        raise RuntimeError(f"Run {run_idx}: Pod did not become Ready within 30s.")

    print(f"Run {run_idx} completed in {ready_time:.2f} seconds.")

    # Retrieve logs showing model download
    time.sleep(1)
    logs = run_cmd(f"kubectl logs {pod_name} -n app -c inference")
    download_log_lines = [line for line in logs.splitlines() if any(kw in line for kw in ["Preparing model", "Downloading archive", "Extracting archive", "successfully loaded"])]

    return {
        "run": run_idx,
        "pod_name": pod_name,
        "cold_start_seconds": round(ready_time, 2),
        "download_log_evidence": download_log_lines
    }


def main():
    print("=" * 60)
    print("Task 4: Cold Start Measurement (3 Runs)")
    print("=" * 60)

    runs = []
    for i in range(1, 4):
        res = run_single_cold_start(i)
        runs.append(res)
        time.sleep(2)

    times = [r["cold_start_seconds"] for r in runs]
    median_time = statistics.median(times)

    # Scale back to 2 replicas for normal operation
    print("\nRestoring deployment to 2 replicas...")
    run_cmd("kubectl scale deployment/inference-service -n app --replicas=2")
    run_cmd("kubectl wait --for=condition=ready pod -l app=inference-service -n app --timeout=60s")

    summary = {
        "runs": runs,
        "cold_start_times_seconds": times,
        "median_cold_start_seconds": round(median_time, 2)
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("COLD START BENCHMARK SUMMARY")
    print("=" * 60)
    for r in runs:
        print(f"Run {r['run']}: {r['cold_start_seconds']}s (Pod: {r['pod_name']})")
        print("  Logs:")
        for log in r["download_log_evidence"]:
            print(f"    {log}")
    print(f"\nMedian Cold-Start Time: {median_time:.2f} seconds")
    print(f"Report saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
