import os
import sys
import glob
import json
import hashlib
import argparse

REQUIRED_KEYS = {"intent", "date", "time", "place"}
ALLOWED_INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events"
}

def clean_data(shards_pattern="worker/shards/shard-*.jsonl",
               out_path="datasets/v1/train.jsonl",
               checksum_path="datasets/v1/train.sha256",
               s3_endpoint="http://127.0.0.1:8333"):
    shard_files = sorted(glob.glob(shards_pattern))
    if not shard_files:
        # Check if files exist directly in worker/shards
        print(f"No shard files found matching pattern: {shards_pattern}")
        sys.exit(1)

    print(f"Found {len(shard_files)} shard files: {shard_files}")

    all_records = []
    seen_ids = set()
    for sf in shard_files:
        with open(sf, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec["id"] in seen_ids:
                        print(f"Warning: duplicate ID {rec['id']} across shards!")
                    seen_ids.add(rec["id"])
                    all_records.append(rec)
                except Exception as e:
                    print(f"Malformed line in {sf}: {line} ({e})")

    # Sort all records by id
    all_records.sort(key=lambda x: x["id"])

    total_input = len(all_records)
    count_a = 0  # not valid JSON
    count_b = 0  # keys not exactly intent, date, time, place
    count_c = 0  # intent not one of the eight
    count_d = 0  # slot value neither null nor in command
    count_duplicates = 0  # duplicate commands
    kept = []

    seen_command_texts = set()

    for rec in all_records:
        cmd_text = rec.get("text", "")
        raw = rec.get("teacher_raw", "")

        # (a) Check valid JSON
        parsed = None
        if isinstance(raw, dict):
            parsed = raw
        else:
            try:
                parsed = json.loads(str(raw).strip())
            except Exception:
                count_a += 1
                continue

        if not isinstance(parsed, dict):
            count_a += 1
            continue

        # (b) Check exact keys
        if set(parsed.keys()) != REQUIRED_KEYS:
            count_b += 1
            continue

        # (c) Check intent
        intent = parsed.get("intent")
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            count_c += 1
            continue

        # (d) Check slot values: must be None or appear in command
        cmd_text_norm = " ".join(cmd_text.lower().split())
        slot_invalid = False
        for slot in ("date", "time", "place"):
            val = parsed.get(slot)
            if val is not None:
                if not isinstance(val, str):
                    slot_invalid = True
                    break
                val_norm = " ".join(val.lower().split())
                if val_norm not in cmd_text_norm:
                    slot_invalid = True
                    break
        if slot_invalid:
            count_d += 1
            continue

        # (e) Duplicate commands (keep the one with the smallest id)
        # Since all_records is sorted by id, the first occurrence is kept.
        norm_cmd = " ".join(cmd_text.lower().split())
        if norm_cmd in seen_command_texts:
            count_duplicates += 1
            continue
        seen_command_texts.add(norm_cmd)

        # Kept record
        kept.append(rec)

    # Verification: total_input == count_a + count_b + count_c + count_d + count_duplicates + len(kept)
    assert total_input == count_a + count_b + count_c + count_d + count_duplicates + len(kept), "Counts do not sum to total input!"

    # Ensure output directory exists
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(checksum_path) or ".", exist_ok=True)

    # Write cleaned train.jsonl
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Compute SHA-256
    sha256 = hashlib.sha256()
    with open(out_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    digest = sha256.hexdigest()

    with open(checksum_path, "w", encoding="utf-8") as f:
        f.write(digest + "\n")

    print("\n" + "=" * 50)
    print("CLEANING COUNTS SUMMARY")
    print("=" * 50)
    print(f"Total input records:               {total_input}")
    print(f"(a) Not valid JSON:                {count_a}")
    print(f"(b) Invalid keys:                  {count_b}")
    print(f"(c) Invalid intent:                {count_c}")
    print(f"(d) Hallucinated slot (not in text):{count_d}")
    print(f"(e) Duplicate commands:            {count_duplicates}")
    print(f"Records kept:                      {len(kept)}")
    print("-" * 50)
    print(f"Sum check: {count_a} + {count_b} + {count_c} + {count_d} + {count_duplicates} + {len(kept)} = {count_a + count_b + count_c + count_d + count_duplicates + len(kept)} (Matches input: {total_input})")
    print(f"SHA-256 Checksum ({checksum_path}): {digest}")
    print("=" * 50 + "\n")

    # Optionally upload to S3 if requested or endpoint reachable
    if s3_endpoint:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                endpoint_url=s3_endpoint,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "any"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "any"),
                region_name="us-east-1"
            )
            print("Uploading cleaned dataset to s3://datasets/v1/train.jsonl...")
            s3.upload_file(out_path, "datasets", "v1/train.jsonl")
            s3.upload_file(checksum_path, "datasets", "v1/train.sha256")
            print("Successfully uploaded train.jsonl and train.sha256 to SeaweedFS S3.")
        except Exception as e:
            print(f"Notice: S3 upload skipped or failed: {e}")

    return {
        "total_input": total_input,
        "rejected_a": count_a,
        "rejected_b": count_b,
        "rejected_c": count_c,
        "rejected_d": count_d,
        "duplicates": count_duplicates,
        "kept": len(kept),
        "sha256": digest
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean worker teacher outputs")
    parser.add_argument("--shards", default="worker/shards/shard-*.jsonl", help="Glob pattern for shard files")
    parser.add_argument("--out", default="datasets/v1/train.jsonl", help="Output train.jsonl path")
    parser.add_argument("--checksum", default="datasets/v1/train.sha256", help="Output checksum path")
    parser.add_argument("--s3-endpoint", default="http://127.0.0.1:8333", help="S3 endpoint URL to upload results")
    args = parser.parse_args()
    clean_data(args.shards, args.out, args.checksum, args.s3_endpoint)
