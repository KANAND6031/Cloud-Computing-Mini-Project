import os
import sys
import time
import subprocess
import urllib.request


def run(cmd, check=True):
    print(f">> {cmd}", flush=True)
    res = subprocess.run(cmd, shell=True, text=True, capture_output=False)
    if check and res.returncode != 0:
        print(f"Command failed with exit code {res.returncode}: {cmd}", file=sys.stderr)
        sys.exit(res.returncode)
    return res.returncode


def setup_system():
    print("=" * 60)
    print("BOOTSTRAPPING SYSTEM: k3d Cluster, SeaweedFS, S3, & Services")
    print("=" * 60)

    # 1. Create k3d cluster if not existing
    print("[1/6] Creating k3d cluster...")
    run("k3d cluster create --config cluster/k3d.yaml || true", check=False)

    # 2. Deploy SeaweedFS in data namespace
    print("[2/6] Deploying SeaweedFS...")
    run("kubectl apply -f deployment/seaweedfs.yaml")
    print("Waiting for SeaweedFS pod to be ready...")
    run("kubectl wait --namespace data --for=condition=ready pod -l app=seaweedfs --timeout=90s")

    # 3. Ensure model artifact exists
    print("[3/6] Verifying model artifacts...")
    model_tar = "models/v1/model.tar.gz"
    if not os.path.exists(model_tar):
        os.makedirs("models/v1", exist_ok=True)
        print("Model weights not present locally; downloading release asset v1.0.0...")
        url = "https://github.com/KANAND6031/cloud/releases/download/v1.0.0/model.tar.gz"
        try:
            urllib.request.urlretrieve(url, model_tar)
            print("Successfully downloaded model.tar.gz")
        except Exception as e:
            print(f"Warning: could not download model release asset: {e}")

    # 4. Upload model and dataset to SeaweedFS via port-forward or k8s job
    print("[4/6] Initializing S3 buckets and uploading artifacts...")
    # Port-forward in background to populate S3
    pf_proc = subprocess.Popen(["kubectl", "port-forward", "-n", "data", "svc/seaweedfs", "8333:8333"])
    time.sleep(3)
    try:
        import boto3
        from botocore.client import Config
        s3 = boto3.client(
            "s3",
            endpoint_url="http://127.0.0.1:8333",
            aws_access_key_id="any",
            aws_secret_access_key="any",
            region_name="us-east-1",
            config=Config(signature_version="s3v4")
        )
        for b in ["datasets", "models"]:
            try:
                s3.create_bucket(Bucket=b)
            except Exception:
                pass
        if os.path.exists("data/commands_pool.jsonl"):
            s3.upload_file("data/commands_pool.jsonl", "datasets", "commands_pool.jsonl")
        if os.path.exists(model_tar):
            s3.upload_file(model_tar, "models", "v1/model.tar.gz")
            print("Uploaded model.tar.gz to s3://models/v1/model.tar.gz")
    except Exception as e:
        print(f"Notice during S3 upload: {e}")
    finally:
        pf_proc.terminate()

    # 5. Build and import Docker image
    print("[5/6] Building and importing container image...")
    run("docker build -t cloud-service:v1 -f service/Dockerfile service")
    run("k3d image import cloud-service:v1 -c cloud-assignment")

    # 6. Deploy inference service and HPA
    print("[6/6] Deploying application and HPA...")
    run("kubectl apply -f deployment/app.yaml")
    run("kubectl apply -f deployment/hpa.yaml")
    print("Waiting for deployment inference-service to be available...")
    run("kubectl wait --namespace app --for=condition=available deployment/inference-service --timeout=120s")

    print("=" * 60)
    print("SUCCESS: System is up and serving at http://localhost:8080/parse")
    print("=" * 60)


if __name__ == "__main__":
    setup_system()
