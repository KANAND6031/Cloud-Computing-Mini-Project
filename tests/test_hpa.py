import os
import sys
import time
import json
import subprocess

OUT_FILE = "results/hpa_scaling_test.json"


def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return res.stdout.strip()


def get_hpa_and_pods():
    hpa_line = run_cmd("kubectl get hpa inference-hpa -n app --no-headers")
    # Columns: NAME REFERENCE TARGETS MINPODS MAXPODS REPLICAS AGE
    pods_out = run_cmd("kubectl get pods -n app -l app=inference-service --no-headers")
    pod_lines = [p for p in pods_out.splitlines() if p.strip()]
    return hpa_line, pod_lines


def main():
    print("=" * 60)
    print("Task 4: HPA Scaling Test (1 -> 2 -> 1 replicas)")
    print("=" * 60)

    # 1. Verify starting replica count is 1
    hpa_line, pods = get_hpa_and_pods()
    print(f"Initial HPA: {hpa_line}")
    print(f"Initial Pods ({len(pods)}):")
    for p in pods:
        print(f"  {p}")

    timeline = []
    t0 = time.time()

    def record_event(phase, hpa, pod_count):
        entry = {
            "elapsed_sec": round(time.time() - t0, 1),
            "phase": phase,
            "hpa": hpa,
            "pod_count": pod_count
        }
        timeline.append(entry)
        print(f"[{entry['elapsed_sec']:5.1f}s] [{phase}] Pods: {pod_count} | HPA: {hpa}")

    record_event("start_idle", hpa_line, len(pods))

    # 2. Launch Locust load test in background
    print("\nStarting Locust load test (4 users, 60s) to trigger scale up...")
    locust_proc = subprocess.Popen(
        [r".\.venv\Scripts\locust.exe", "-f", "tools/locustfile.py", "--headless",
         "--users", "4", "--spawn-rate", "4", "--run-time", "60s", "--host", "http://localhost:8080"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    scaled_to_2 = False
    scale_up_time = None

    # Monitor scale-up
    print("Monitoring scale-up to 2 replicas...")
    while locust_proc.poll() is None:
        hpa_line, pods = get_hpa_and_pods()
        record_event("under_load", hpa_line, len(pods))
        if len(pods) >= 2 and not scaled_to_2:
            scaled_to_2 = True
            scale_up_time = round(time.time() - t0, 1)
            print(f"--> SCALE-UP DETECTED at {scale_up_time}s! Replicas reached 2.")
        time.sleep(3)

    print("\nLocust load test finished. Waiting for scale-down to 1 replica...")
    scaled_to_1 = False
    scale_down_time = None

    # Monitor scale-down (HPA behavior stabilizationWindowSeconds: 30)
    max_wait = 120
    wait_start = time.time()
    while time.time() - wait_start < max_wait:
        hpa_line, pods = get_hpa_and_pods()
        record_event("cooling_down", hpa_line, len(pods))
        if scaled_to_2 and len(pods) == 1:
            scaled_to_1 = True
            scale_down_time = round(time.time() - t0, 1)
            print(f"--> SCALE-DOWN DETECTED at {scale_down_time}s! Replicas back down to 1.")
            break
        time.sleep(4)

    summary = {
        "success": scaled_to_2 and scaled_to_1,
        "scaled_up_to_2": scaled_to_2,
        "scaled_up_at_sec": scale_up_time,
        "scaled_down_to_1": scaled_to_1,
        "scaled_down_at_sec": scale_down_time,
        "timeline": timeline
    }

    os.makedirs(os.path.dirname(OUT_FILE) or ".", exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("HPA SCALING TEST RESULT")
    print("=" * 60)
    print(f"Scaled 1 -> 2 Replicas: {scaled_to_2} (at {scale_up_time}s)")
    print(f"Scaled 2 -> 1 Replicas: {scaled_to_1} (at {scale_down_time}s)")
    print(f"Results saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
