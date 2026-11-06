import os
import sys
import json
import time
import urllib.request
import urllib.error
import boto3

def get_s3_client(endpoint_url):
    key_id = os.environ.get("AWS_ACCESS_KEY_ID", "any")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY", "any")
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=key_id,
        aws_secret_access_key=secret_key,
        region_name="us-east-1"
    )

def main():
    shard_index = int(os.environ.get("SHARD_INDEX", "0"))
    shard_count = int(os.environ.get("SHARD_COUNT", "2"))
    s3_endpoint = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333")
    teacher_url = os.environ.get("TEACHER_URL", "http://127.0.0.1:11434")
    prompt_file = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")
    data_file = os.environ.get("DATA_FILE", "data/commands_pool.jsonl")
    output_dir = os.environ.get("OUTPUT_DIR", "worker/shards")

    print(f"Starting worker: SHARD_INDEX={shard_index}, SHARD_COUNT={shard_count}")
    print(f"Teacher URL: {teacher_url}, S3 Endpoint: {s3_endpoint}")

    os.makedirs(output_dir, exist_ok=True)
    shard_file = os.path.join(output_dir, f"shard-{shard_index}.jsonl")

    # Read prompt template
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt_template = f.read().strip()
    else:
        prompt_template = """You are a voice assistant command parser. Return ONLY a single JSON object with exactly four keys: "intent", "date", "time", "place".

Allowed intents:
- alarm_set
- alarm_query
- calendar_set
- calendar_query
- calendar_remove
- weather_query
- datetime_query
- recommendation_events

Rules:
1. "intent" must be one of the eight allowed intents.
2. "date", "time", "place" must be extracted exactly as they appear in the command, or null if not present.
3. Remove leading prepositions like at, on, in, or for.
4. Output nothing else except the JSON object.

Command: {command}
JSON:"""

    # Ensure data_file exists
    s3 = None
    try:
        s3 = get_s3_client(s3_endpoint)
    except Exception as e:
        print(f"Warning: could not create s3 client: {e}")

    if not os.path.exists(data_file):
        print(f"Data file {data_file} not found locally, downloading from S3 datasets/commands_pool.jsonl...")
        os.makedirs(os.path.dirname(data_file) or ".", exist_ok=True)
        if s3:
            s3.download_file("datasets", "commands_pool.jsonl", data_file)
            print(f"Downloaded {data_file}")
        else:
            raise RuntimeError(f"Cannot download {data_file} without S3 connection")

    # Read all commands
    with open(data_file, "r", encoding="utf-8") as f:
        all_commands = [json.loads(line.strip()) for line in f if line.strip()]

    total_pool = len(all_commands)
    # Filter by shard
    my_commands = [
        (idx, cmd) for idx, cmd in enumerate(all_commands)
        if idx % shard_count == shard_index
    ]
    print(f"Worker {shard_index}: Assigned {len(my_commands)} of {total_pool} commands")

    # Resume capability: check if shard_file already has entries
    processed_ids = set()
    if os.path.exists(shard_file):
        with open(shard_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        processed_ids.add(record["id"])
                    except Exception:
                        pass
        print(f"Worker {shard_index}: Resuming. Already processed {len(processed_ids)} commands.")

    out_f = open(shard_file, "a", encoding="utf-8")

    generate_url = f"{teacher_url.rstrip('/')}/api/generate"

    count = 0
    t_start = time.time()
    for line_num, cmd in my_commands:
        cmd_id = cmd["id"]
        cmd_text = cmd["text"]

        if cmd_id in processed_ids:
            continue

        prompt = prompt_template.replace("{command}", cmd_text)
        payload = json.dumps({
            "model": "phi3.5",
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0,
                "seed": 42,
                "num_predict": 80
            }
        }).encode("utf-8")

        # Retry loop
        success = False
        raw_output = ""
        for attempt in range(5):
            try:
                req = urllib.request.Request(
                    generate_url,
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    raw_output = resp_data.get("response", "").strip()
                    success = True
                    break
            except Exception as e:
                print(f"Worker {shard_index} [{cmd_id}] error on attempt {attempt+1}: {e}")
                time.sleep(1 + attempt)

        if not success:
            raw_output = '{"error": "failed_to_generate"}'

        out_record = {
            "id": cmd_id,
            "text": cmd_text,
            "teacher_raw": raw_output
        }
        out_f.write(json.dumps(out_record, ensure_ascii=False) + "\n")
        out_f.flush()
        processed_ids.add(cmd_id)
        count += 1

        if count % 100 == 0 or count == len(my_commands):
            elapsed = time.time() - t_start
            rate = count / elapsed if elapsed > 0 else 0
            print(f"Worker {shard_index}: Processed {count}/{len(my_commands)} (Total done: {len(processed_ids)}/{len(my_commands)}) at {rate:.2f} cmd/s")

    out_f.close()
    print(f"Worker {shard_index}: Finished generating all assigned commands.")

    # Upload to SeaweedFS S3
    if s3:
        s3_key = f"teacher/shard-{shard_index}.jsonl"
        print(f"Uploading {shard_file} to s3://datasets/{s3_key}...")
        try:
            s3.upload_file(shard_file, "datasets", s3_key)
            print(f"Successfully uploaded s3://datasets/{s3_key}")
        except Exception as e:
            print(f"Error uploading to S3: {e}")

if __name__ == "__main__":
    main()
