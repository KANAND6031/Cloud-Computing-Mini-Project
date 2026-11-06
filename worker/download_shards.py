import os
import boto3

def download_shards(endpoint_url="http://127.0.0.1:8333", out_dir="worker/shards"):
    os.makedirs(out_dir, exist_ok=True)
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id="any",
        aws_secret_access_key="any",
        region_name="us-east-1"
    )

    objects = s3.list_objects_v2(Bucket="datasets", Prefix="teacher/")
    contents = objects.get("Contents", [])
    print(f"Found {len(contents)} objects under teacher/ in bucket datasets:")
    for obj in contents:
        key = obj["Key"]
        filename = os.path.basename(key)
        target = os.path.join(out_dir, filename)
        print(f"Downloading s3://datasets/{key} ({obj['Size']} bytes) -> {target}...")
        s3.download_file("datasets", key, target)
        print(f"Downloaded {target}")

if __name__ == "__main__":
    download_shards()
