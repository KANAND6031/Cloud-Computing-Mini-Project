import os
import sys
import time
import json
import subprocess
import threading
import urllib.request
import urllib.error

CONTAINER_NAME = "service-test"
ENDPOINT = "http://localhost:8000"
VAL_PATH = "data/validation.jsonl"
OUT_REPORT = "results/task3_limits_test.json"

peak_mem_mib = 0.0
peak_mem_str = ""
monitoring = True


def monitor_memory():
    global peak_mem_mib, peak_mem_str, monitoring
    while monitoring:
        try:
            res = subprocess.run(
                ["docker", "stats", CONTAINER_NAME, "--no-stream", "--format", "{{.MemUsage}}"],
                capture_output=True,
                text=True,
                timeout=3
            )
            out = res.stdout.strip()
            if out and "/" in out:
                used_str = out.split("/")[0].strip()
                val = 0.0
                if "GiB" in used_str:
                    val = float(used_str.replace("GiB", "").strip()) * 1024.0
                elif "MiB" in used_str:
                    val = float(used_str.replace("MiB", "").strip())
                elif "KiB" in used_str:
                    val = float(used_str.replace("KiB", "").strip()) / 1024.0

                if val > peak_mem_mib:
                    peak_mem_mib = val
                    peak_mem_str = out
        except Exception:
            pass
        time.sleep(0.2)


def main():
    global monitoring
    print("=" * 60)
    print("Task 3: Under-Limits Sequential 50 Requests Test")
    print(f"Container: {CONTAINER_NAME} (1 CPU, 1 GiB memory limit)")
    print("=" * 60)

    # 1. Check healthz & readyz
    print("\n1. Verifying probes...")
    try:
        with urllib.request.urlopen(f"{ENDPOINT}/healthz", timeout=5) as r:
            assert r.status == 200
            print("  /healthz returned HTTP 200 OK")
        with urllib.request.urlopen(f"{ENDPOINT}/readyz", timeout=5) as r:
            assert r.status == 200
            print("  /readyz returned HTTP 200 OK")
    except Exception as e:
        sys.exit(f"Probe verification failed: {e}")

    # 2. Start memory monitor thread
    monitor_thread = threading.Thread(target=monitor_memory, daemon=True)
    monitor_thread.start()

    # 3. Read 50 commands
    records = []
    with open(VAL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
            if len(records) >= 50:
                break

    print(f"\n2. Sending {len(records)} requests sequentially to {ENDPOINT}/parse...")
    latencies = []
    success_count = 0
    served_by_counter = {}
    model_version_counter = {}

    start_total = time.time()
    for idx, rec in enumerate(records, 1):
        cmd_text = rec["text"]
        payload = json.dumps({"text": cmd_text}).encode("utf-8")
        req = urllib.request.Request(
            f"{ENDPOINT}/parse",
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        t0 = time.time()
        status_code = None
        headers = {}
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status_code = resp.status
                headers = dict(resp.headers)
                _ = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            status_code = e.code
            headers = dict(e.headers)
            _ = e.read()
        except Exception as e:
            print(f"  Request #{idx} ERROR: {e}")
            continue

        lat_ms = (time.time() - t0) * 1000.0
        latencies.append(lat_ms)

        srv = headers.get("x-served-by", "unknown")
        ver = headers.get("x-model-version", "unknown")
        served_by_counter[srv] = served_by_counter.get(srv, 0) + 1
        model_version_counter[ver] = model_version_counter.get(ver, 0) + 1

        if status_code == 200:
            success_count += 1

        if idx % 10 == 0 or idx == len(records):
            print(f"  Completed {idx}/50 requests | Latency: {lat_ms:.1f}ms | Status: {status_code} | Peak Mem: {peak_mem_mib:.1f} MiB")

    total_time = time.time() - start_total
    monitoring = False
    time.sleep(0.5)

    # 4. Check container alive status
    res = subprocess.run(["docker", "ps", "-f", f"name={CONTAINER_NAME}", "--format", "{{.Status}}"], capture_output=True, text=True)
    container_alive = bool(res.stdout.strip())

    # Get final docker stats
    res_stats = subprocess.run(["docker", "stats", CONTAINER_NAME, "--no-stream"], capture_output=True, text=True)
    final_stats_output = res_stats.stdout.strip()

    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.5)] if latencies_sorted else 0
    p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)] if latencies_sorted else 0

    report = {
        "total_requests": len(records),
        "successful_requests": success_count,
        "failed_requests": len(records) - success_count,
        "container_alive": container_alive,
        "oom_killed": not container_alive,
        "peak_memory_mib": round(peak_mem_mib, 2),
        "peak_memory_raw": peak_mem_str,
        "latency_ms": {
            "p50": round(p50, 2),
            "p95": round(p95, 2),
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0
        },
        "total_duration_sec": round(total_time, 2),
        "served_by_distribution": served_by_counter,
        "model_version_distribution": model_version_counter,
        "docker_stats_snapshot": final_stats_output
    }

    os.makedirs(os.path.dirname(OUT_REPORT) or ".", exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Total Requests: {report['total_requests']}")
    print(f"Successful (HTTP 200): {report['successful_requests']}")
    print(f"OOM Killed: {report['oom_killed']}")
    print(f"Container Alive: {report['container_alive']}")
    print(f"Peak Memory: {report['peak_memory_mib']:.2f} MiB ({report['peak_memory_raw']})")
    print(f"p50 Latency: {report['latency_ms']['p50']} ms")
    print(f"p95 Latency: {report['latency_ms']['p95']} ms")
    print(f"Served By Header: {served_by_counter}")
    print(f"Model Version Header: {model_version_counter}")
    print("\nDocker stats snapshot:\n" + final_stats_output)
    print(f"\nReport written to {OUT_REPORT}")


if __name__ == "__main__":
    main()
