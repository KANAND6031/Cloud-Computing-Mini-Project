import glob
import json
import sys

def verify(pool_path="data/commands_pool.jsonl", shards_pattern="worker/shards/shard-*.jsonl"):
    with open(pool_path, "r", encoding="utf-8") as f:
        pool_ids = [json.loads(line.strip())["id"] for line in f if line.strip()]

    pool_set = set(pool_ids)
    print(f"Total commands in pool: {len(pool_ids)} (Unique IDs: {len(pool_set)})")

    shard_files = sorted(glob.glob(shards_pattern))
    print(f"Checking shard files: {shard_files}")

    all_shard_ids = []
    seen = {}
    for sf in shard_files:
        with open(sf, "r", encoding="utf-8") as f:
            count = 0
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                cid = rec["id"]
                all_shard_ids.append(cid)
                if cid in seen:
                    print(f"ERROR: Duplicate ID {cid} found in {sf} (previously seen in {seen[cid]})")
                seen[cid] = sf
                count += 1
            print(f"  {sf}: {count} records")

    shard_set = set(all_shard_ids)
    print(f"Total records in shards: {len(all_shard_ids)} (Unique IDs: {len(shard_set)})")

    missing = pool_set - shard_set
    extra = shard_set - pool_set

    if missing:
        print(f"ERROR: {len(missing)} missing IDs: {list(missing)[:5]}...")
    if extra:
        print(f"ERROR: {len(extra)} extra IDs: {list(extra)[:5]}...")
    if len(all_shard_ids) != len(shard_set):
        print(f"ERROR: Found {len(all_shard_ids) - len(shard_set)} repeated IDs!")

    if not missing and not extra and len(all_shard_ids) == len(pool_ids):
        print("SUCCESS: Every command ID appears in exactly one shard output with no gaps and no repeats!")
        return True
    else:
        print("VERIFICATION FAILED")
        return False

if __name__ == "__main__":
    ok = verify()
    sys.exit(0 if ok else 1)
