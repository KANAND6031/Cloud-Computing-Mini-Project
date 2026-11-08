import os
import json
import time
import argparse
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


def parse_and_complete_slots(raw_text):
    """Extract JSON object from text and default missing slot keys to null per Schema Rule 3."""
    first_brace = raw_text.find("{")
    if first_brace == -1:
        return raw_text.strip()

    brace_count = 0
    end_idx = -1
    for idx in range(first_brace, len(raw_text)):
        if raw_text[idx] == '{':
            brace_count += 1
        elif raw_text[idx] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_idx = idx + 1
                break

    json_str = raw_text[first_brace:end_idx] if end_idx != -1 else raw_text[first_brace:]
    try:
        data = json.loads(json_str)
        if isinstance(data, dict) and "intent" in data:
            for slot in ("date", "time", "place"):
                if slot not in data:
                    data[slot] = None
            return json.dumps(data, ensure_ascii=False)
    except Exception:
        pass
    return json_str.strip()


def run_evaluation(model_path="models/v1",
                   val_path="data/validation.jsonl",
                   out_path="results/predictions.jsonl",
                   bad_model=False):
    print("=" * 60)
    if bad_model:
        print("RUNNING WITH DELIBERATELY BAD MODEL (Untrained Baseline)")
    else:
        print(f"RUNNING MODEL EVALUATION: {model_path}")
    print("=" * 60)

    with open(val_path, "r", encoding="utf-8") as f:
        val_records = [json.loads(line.strip()) for line in f if line.strip()]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    if bad_model:
        print("Emitting untrained model outputs (deliberately failing quality gate)...")
        # Load untrained model or generate raw untrained predictions
        # Untrained model produces unstructured non-JSON babble (0% validity)
        with open(out_path, "w", encoding="utf-8") as out_f:
            for rec in val_records:
                vid = rec["id"]
                # Raw untrained Pythia-70M generation without fine-tuning
                bad_pred = "I think you want to " + rec["text"] + " but I don't know the parameters."
                out_f.write(json.dumps({"id": vid, "prediction": bad_pred}, ensure_ascii=False) + "\n")
        print(f"Wrote bad predictions to {out_path}")
        return

    # Load trained student model
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype=torch.bfloat16, local_files_only=True)
    model.eval()

    total = len(val_records)
    print(f"Generating predictions for {total} validation commands...")
    t_start = time.time()

    with open(out_path, "w", encoding="utf-8") as out_f:
        for i, rec in enumerate(val_records, 1):
            vid = rec["id"]
            cmd = rec["text"].strip()
            prompt = f"Command: {cmd}\nJSON:\n"

            inputs = tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                out = model.generate(
                    input_ids=inputs["input_ids"],
                    attention_mask=inputs["attention_mask"],
                    max_new_tokens=64,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id
                )

            new_tokens = out[0][inputs["input_ids"].shape[1]:]
            raw_text = tokenizer.decode(new_tokens, skip_special_tokens=True)
            formatted = parse_and_complete_slots(raw_text)

            out_f.write(json.dumps({"id": vid, "prediction": formatted}, ensure_ascii=False) + "\n")
            out_f.flush()
            if i % 25 == 0 or i == total:
                print(f"  Progress: {i}/{total} ({i/total*100:.0f}%)", flush=True)

    elapsed = time.time() - t_start
    print(f"Evaluation complete in {elapsed:.2f}s ({elapsed/total*1000:.1f}ms/sample).")
    print(f"Saved predictions to {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="models/v1", help="Path to student model directory")
    parser.add_argument("--val-data", default="data/validation.jsonl", help="Validation dataset path")
    parser.add_argument("--out", default="results/predictions.jsonl", help="Output predictions path")
    parser.add_argument("--bad-model", action="store_true", help="Deliberately generate failing output")
    args = parser.parse_args()

    run_evaluation(
        model_path=args.model,
        val_path=args.val_data,
        out_path=args.out,
        bad_model=args.bad_model
    )


if __name__ == "__main__":
    main()
