import os
import sys
import time
import json
import subprocess
import threading


def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()


pod_metrics = {}
stop_monitoring = False


def monitor_top_pods(interval=5):
    global pod_metrics, stop_monitoring
    while not stop_monitoring:
        try:
            out = run_cmd("kubectl top pods -n app --no-headers")
            # Sample line: inference-service-5c7c4ffbdf-jtnt9   5m   359Mi
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0].startswith("inference-service"):
                    pname = parts[0]
                    cpu_raw = parts[1]
                    mem_raw = parts[2]

                    # Parse cpu in millicores
                    cpu_m = 0
                    if cpu_raw.endswith("m"):
                        cpu_m = int(cpu_raw[:-1])
                    elif cpu_raw.isdigit():
                        cpu_m = int(cpu_raw) * 1000

                    # Parse mem in MiB
                    mem_mib = 0.0
                    if mem_raw.endswith("Mi"):
                        mem_mib = float(mem_raw[:-2])
                    elif mem_raw.endswith("Gi"):
                        mem_mib = float(mem_raw[:-2]) * 1024.0

                    if pname not in pod_metrics:
                        pod_metrics[pname] = {"cpu_m": [], "mem_mib": []}
                    pod_metrics[pname]["cpu_m"].append(cpu_m)
                    pod_metrics[pname]["mem_mib"].append(mem_mib)
        except Exception:
            pass
        time.sleep(interval)


def main():
    global stop_monitoring
    print("=" * 60)
    print("TASK 7: PERFORMANCE BENCHMARK (LOCUST 4 USERS, 2 MINUTES)")
    print("=" * 60)

    # 1. Ensure 2 Ready replicas
    print("[1/4] Scaling to 2 replicas and waiting for readiness...")
    run_cmd("kubectl scale deployment inference-service -n app --replicas=2")
    run_cmd("kubectl wait --for=condition=ready pod -l app=inference-service -n app --timeout=90s")

    ready_pods = run_cmd("kubectl get pods -n app -l app=inference-service --no-headers").splitlines()
    print("Ready pods:")
    for p in ready_pods:
        print(" ", p)

    # 2. Start resource monitoring thread
    print("\n[2/4] Starting kubectl top monitoring thread...")
    t_mon = threading.Thread(target=monitor_top_pods, args=(5,), daemon=True)
    t_mon.start()

    # 3. Run standard Locust load test
    print("\n[3/4] Launching Locust load test (4 users, 2 minutes)...")
    env = os.environ.copy()
    env["LOADTEST_HEADERS_OUT"] = "results/task7_headers.json"
    env["LOADTEST_TEXTS"] = "data/validation.jsonl"

    csv_prefix = "results/task7_loadtest"
    cmd = [
        sys.executable, "-m", "locust",
        "-f", "tools/locustfile.py",
        "--headless",
        "--users", "4",
        "--spawn-rate", "4",
        "--run-time", "2m",
        "--host", "http://localhost:8080",
        "--csv", csv_prefix
    ]

    t_start = time.time()
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    t_elapsed = time.time() - t_start
    print(f"Locust finished in {t_elapsed:.1f}s.")
    print("Locust STDOUT:\n", proc.stdout)
    if proc.stderr:
        print("Locust STDERR:\n", proc.stderr)

    # Stop monitoring
    stop_monitoring = True
    time.sleep(1)

    # 4. Parse Locust stats CSV
    print("\n[4/4] Aggregating results...")
    stats_csv = f"{csv_prefix}_stats.csv"
    stats_data = {}
    if os.path.exists(stats_csv):
        import csv
        with open(stats_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Name") == "/parse" or row.get("Name") == "Aggregated":
                    stats_data[row.get("Name")] = row

    parse_stats = stats_data.get("/parse", stats_data.get("Aggregated", {}))
    req_count = int(parse_stats.get("Request Count", 0))
    fail_count = int(parse_stats.get("Failure Count", 0))
    p50_latency = float(parse_stats.get("50%", parse_stats.get("Median Response Time", 0)))
    p95_latency = float(parse_stats.get("95%", 0))
    rps = float(parse_stats.get("Requests/s", 0))
    error_rate = (fail_count / req_count * 100.0) if req_count > 0 else 0.0

    # Resource summary
    resource_summary = {}
    for pname, metrics in pod_metrics.items():
        cpu_list = metrics["cpu_m"]
        mem_list = metrics["mem_mib"]
        resource_summary[pname] = {
            "avg_cpu_millicores": round(sum(cpu_list) / len(cpu_list), 1) if cpu_list else 0,
            "peak_cpu_millicores": max(cpu_list) if cpu_list else 0,
            "avg_memory_mib": round(sum(mem_list) / len(mem_list), 1) if mem_list else 0,
            "peak_memory_mib": max(mem_list) if mem_list else 0
        }

    # Headers summary
    headers_data = {}
    if os.path.exists("results/task7_headers.json"):
        with open("results/task7_headers.json", "r", encoding="utf-8") as f:
            headers_data = json.load(f)

    # Load cold start median from Task 4
    cold_start_median_s = 7.13
    if os.path.exists("results/cold_start_test.json"):
        try:
            with open("results/cold_start_test.json", "r", encoding="utf-8") as f:
                cs_data = json.load(f)
                cold_start_median_s = cs_data.get("median_cold_start_seconds", 7.13)
        except Exception:
            pass

    final_report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "run_time_seconds": round(t_elapsed, 1),
        "total_requests": req_count,
        "failed_requests": fail_count,
        "error_rate_pct": round(error_rate, 2),
        "throughput_rps": round(rps, 2),
        "latency_ms": {
            "p50_median": p50_latency,
            "p95": p95_latency,
            "avg": float(parse_stats.get("Average Response Time", 0)),
            "min": float(parse_stats.get("Min Response Time", 0)),
            "max": float(parse_stats.get("Max Response Time", 0))
        },
        "pod_resources": resource_summary,
        "traffic_distribution": headers_data,
        "cold_start_median_seconds": cold_start_median_s
    }

    out_file = "results/task7_benchmark.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2)

    print("=" * 60)
    print("TASK 7 BENCHMARK SUMMARY:")
    print(f"Total Requests:      {req_count}")
    print(f"Failed Requests:     {fail_count} ({error_rate:.2f}%)")
    print(f"Throughput:          {rps:.2f} req/s ({rps * 3600:.0f} req/hr)")
    print(f"p50 Latency:         {p50_latency:.0f} ms")
    print(f"p95 Latency:         {p95_latency:.0f} ms")
    print(f"Cold Start (Median): {cold_start_median_s:.2f} s")
    print("Pod Resource Utilisation:")
    for pname, r in resource_summary.items():
        print(f"  {pname}: Peak CPU = {r['peak_cpu_millicores']}m, Peak Mem = {r['peak_memory_mib']} MiB")
    print("=" * 60)
    print(f"Saved report to {out_file}")


if __name__ == "__main__":
    main()
