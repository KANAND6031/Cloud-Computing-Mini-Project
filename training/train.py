import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import sys
import time
import json
import yaml
import random
import shutil
import tarfile
import hashlib
import argparse
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForCausalLM, get_linear_schedule_with_warmup

# Set reproducible seeds
def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

class DistillationDataset(Dataset):
    def __init__(self, records, tokenizer, max_length=128):
        self.examples = []
        for rec in records:
            cmd = rec["text"].strip()
            # Canonical compact JSON string
            raw = rec.get("teacher_raw", "{}")
            try:
                if isinstance(raw, str):
                    parsed = json.loads(raw)
                else:
                    parsed = raw
                target_json = json.dumps(parsed, separators=(',', ': '))
            except Exception:
                target_json = raw.strip() if isinstance(raw, str) else "{}"

            prompt_text = f"Command: {cmd}\nJSON:\n"
            prompt_ids = tokenizer.encode(prompt_text, add_special_tokens=False)
            target_ids = tokenizer.encode(f"{target_json}<|endoftext|>", add_special_tokens=False)
            full_ids = prompt_ids + target_ids

            if len(full_ids) > max_length:
                full_ids = full_ids[:max_length]

            # Mask prompt tokens with -100 so causal LM only computes loss on target JSON
            prompt_len = min(len(prompt_ids), len(full_ids))
            labels = [-100] * prompt_len + list(full_ids[prompt_len:])

            self.examples.append({
                "input_ids": torch.tensor(full_ids, dtype=torch.long),
                "labels": torch.tensor(labels, dtype=torch.long)
            })

    def __len__(self):
        return len(self.examples)

    def __getitem__(self, idx):
        return self.examples[idx]

def collate_fn(batch, pad_token_id=0):
    max_len = max(len(x["input_ids"]) for x in batch)
    input_ids = []
    labels = []
    attention_mask = []

    for x in batch:
        cur_len = len(x["input_ids"])
        pad_len = max_len - cur_len
        # Right padding
        inp = torch.cat([x["input_ids"], torch.full((pad_len,), pad_token_id, dtype=torch.long)])
        lbl = torch.cat([x["labels"], torch.full((pad_len,), -100, dtype=torch.long)])
        mask = torch.cat([torch.ones(cur_len, dtype=torch.long), torch.zeros(pad_len, dtype=torch.long)])
        input_ids.append(inp)
        labels.append(lbl)
        attention_mask.append(mask)

    return {
        "input_ids": torch.stack(input_ids),
        "labels": torch.stack(labels),
        "attention_mask": torch.stack(attention_mask)
    }

def train_model(config_path="training/config.yaml",
                subset=None,
                output_dir="models/v1",
                data_path="datasets/v1/train.jsonl",
                loss_csv="training/loss.csv",
                epochs_override=None,
                seed_override=None,
                s3_endpoint="http://127.0.0.1:8333"):

    # 1. Read config.yaml
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    seed = int(seed_override if seed_override is not None else config.get("seed", 42))
    learning_rate = float(config.get("learning_rate", 5e-4))
    batch_size = int(config.get("batch_size", 16))
    epochs = int(epochs_override if epochs_override is not None else config.get("epochs", 3))
    max_seq_length = int(config.get("max_seq_length", 128))

    print("=" * 60)
    print(f"TRAINING PYTHIA-70M (Sequence-Level Distillation)")
    print(f"Config: seed={seed}, lr={learning_rate}, batch_size={batch_size}, epochs={epochs}, max_seq_length={max_seq_length}")
    print(f"Output directory: {output_dir}")
    print("=" * 60)

    set_seed(seed)

    # 2. Load dataset
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Cleaned training dataset {data_path} not found!")

    records = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Task requires training on the first 1,500 records of train.jsonl
    target_count = int(subset) if subset else 1500
    records = records[:target_count]
    print(f"Loaded {len(records)} training examples (requested subset: {target_count})")

    # 3. Load Model and Tokenizer
    model_name = "EleutherAI/pythia-70m"
    print(f"Loading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    pad_id = tokenizer.pad_token_id

    model = AutoModelForCausalLM.from_pretrained(model_name, torch_dtype=torch.bfloat16, local_files_only=True)
    model.train()

    dataset = DistillationDataset(records, tokenizer, max_length=max_seq_length)
    dataloader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=lambda b: collate_fn(b, pad_token_id=pad_id)
    )

    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=0.01)
    total_steps = len(dataloader) * epochs
    warmup_steps = int(0.05 * total_steps)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

    epoch_losses = []

    for ep in range(1, epochs + 1):
        total_loss = 0.0
        steps = 0
        t_ep_start = time.time()
        for b_idx, batch in enumerate(dataloader, 1):
            optimizer.zero_grad()
            outputs = model(
                input_ids=batch["input_ids"],
                attention_mask=batch["attention_mask"],
                labels=batch["labels"]
            )
            loss = outputs.loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            total_loss += loss.item()
            steps += 1
            print(f"  [Epoch {ep}/{epochs}] Batch {b_idx}/{len(dataloader)} - Loss: {loss.item():.4f}", flush=True)

        avg_loss = total_loss / max(steps, 1)
        epoch_losses.append((ep, avg_loss))
        ep_duration = time.time() - t_ep_start
        print(f"Epoch {ep}/{epochs} Finished in {ep_duration:.1f}s - Avg Loss: {avg_loss:.4f}", flush=True)

    # 4. Save loss.csv
    os.makedirs(os.path.dirname(loss_csv) or ".", exist_ok=True)
    with open(loss_csv, "w", encoding="utf-8") as f:
        f.write("epoch,loss\n")
        for ep, l in epoch_losses:
            f.write(f"{ep},{l:.4f}\n")
    print(f"Saved training loss to {loss_csv}", flush=True)

    # 5. Save model and tokenizer
    os.makedirs(output_dir, exist_ok=True)
    print(f"Saving model and tokenizer to {output_dir}...", flush=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"Saved model and tokenizer to {output_dir}", flush=True)

    # 6. Create archive (GitHub Release asset) and sha256 checksum
    version_tag = os.path.basename(output_dir.rstrip("/\\")) # v1 or v2
    asset_name = "model.tar.gz"
    asset_path = os.path.join(output_dir, asset_name)
    print(f"Creating release asset archive {asset_path}...", flush=True)
    with tarfile.open(asset_path, "w:gz") as tar:
        for fname in sorted(os.listdir(output_dir)):
            if fname.endswith(".tar.gz") or fname.endswith(".sha256"):
                continue
            fpath = os.path.join(output_dir, fname)
            if os.path.isfile(fpath):
                print(f"  Archiving {fname}...", flush=True)
                tar.add(fpath, arcname=fname)
    print(f"Created release asset: {asset_path}", flush=True)

    # Compute sha256 of the release asset
    print(f"Computing SHA-256 checksum for {asset_name}...", flush=True)
    sha256 = hashlib.sha256()
    with open(asset_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    asset_checksum = sha256.hexdigest()

    checksum_file = os.path.join(output_dir, "model.sha256")
    with open(checksum_file, "w", encoding="utf-8") as f:
        f.write(f"{asset_checksum}  {asset_name}\n")
    print(f"Saved checksum to {checksum_file}: {asset_checksum}", flush=True)

    # Also create versioned copy e.g. model-v1.tar.gz
    if version_tag and version_tag != "models":
        v_asset_path = os.path.join(output_dir, f"model-{version_tag}.tar.gz")
        shutil.copy2(asset_path, v_asset_path)
        print(f"Created versioned copy: {v_asset_path}", flush=True)

    # 7. Upload model files and archive to SeaweedFS S3 bucket `models`
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
            norm_dir = output_dir.replace("\\", "/").strip("/")
            version_sub = os.path.basename(norm_dir)
            print(f"Uploading artifacts in {output_dir} to s3://models/...", flush=True)
            for fname in sorted(os.listdir(output_dir)):
                fpath = os.path.join(output_dir, fname)
                if os.path.isfile(fpath):
                    s3_key1 = f"{version_sub}/{fname}"
                    s3_key2 = f"models/{version_sub}/{fname}"
                    print(f"  Uploading {fname} ({os.path.getsize(fpath)} bytes) -> s3://models/{s3_key1}...", flush=True)
                    s3.upload_file(fpath, "models", s3_key1)
                    s3.upload_file(fpath, "models", s3_key2)
            print("Successfully uploaded model artifacts to SeaweedFS S3.", flush=True)
        except Exception as e:
            print(f"Notice: S3 upload skipped or failed: {e}", flush=True)

    return {
        "losses": epoch_losses,
        "checksum": asset_checksum,
        "asset_path": asset_path
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fine-tune Pythia-70M on sequence-level distillation dataset")
    parser.add_argument("--config", default="training/config.yaml", help="Path to config.yaml")
    parser.add_argument("--subset", type=int, default=None, help="Train on first N records only")
    parser.add_argument("--output-dir", default="models/v1", help="Output directory for trained model")
    parser.add_argument("--epochs", type=int, default=None, help="Override number of epochs")
    parser.add_argument("--seed", type=int, default=None, help="Override random seed")
    parser.add_argument("--loss-csv", default="training/loss.csv", help="Path to output loss.csv")
    parser.add_argument("--s3-endpoint", default="http://127.0.0.1:8333", help="S3 endpoint URL")
    args = parser.parse_args()

    train_model(
        config_path=args.config,
        subset=args.subset,
        output_dir=args.output_dir,
        epochs_override=args.epochs,
        seed_override=args.seed,
        loss_csv=args.loss_csv,
        s3_endpoint=args.s3_endpoint
    )
