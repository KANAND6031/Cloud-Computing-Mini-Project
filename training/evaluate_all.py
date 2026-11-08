import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
import time
import json
import urllib.request
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

def evaluate_teacher(val_path="data/validation.jsonl",
                     prompt_path="prompts/teacher_prompt.txt",
                     out_pred_path="results/teacher_predictions.jsonl",
                     ollama_url="http://127.0.0.1:11434"):
    print("=" * 60)
    print("Evaluating TEACHER (Phi-3.5 via Ollama)...")
    print("=" * 60)
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_tmpl = f.read().strip()

    with open(val_path, "r", encoding="utf-8") as f:
        val_records = [json.loads(line.strip()) for line in f if line.strip()]

    os.makedirs(os.path.dirname(out_pred_path) or ".", exist_ok=True)
    generate_url = f"{ollama_url.rstrip('/')}/api/generate"

    with open(out_pred_path, "w", encoding="utf-8") as out_f:
        for i, rec in enumerate(val_records, 1):
            vid = rec["id"]
            text = rec["text"]
            p = prompt_tmpl.replace("{command}", text)
            payload = json.dumps({
                "model": "phi3.5",
                "prompt": p,
                "format": "json",
                "stream": False,
                "options": {
                    "temperature": 0,
                    "seed": 42,
                    "num_predict": 80
                }
            }).encode("utf-8")

            raw_resp = ""
            for attempt in range(3):
                try:
                    req = urllib.request.Request(generate_url, data=payload, headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        res_data = json.loads(resp.read().decode("utf-8"))
                        raw_resp = res_data.get("response", "").strip()
                        break
                except Exception as e:
                    print(f"Teacher eval [{vid}] retry {attempt+1}: {e}")

            pred_obj = {"id": vid, "prediction": raw_resp}
            out_f.write(json.dumps(pred_obj, ensure_ascii=False) + "\n")
            out_f.flush()
            if i % 25 == 0 or i == len(val_records):
                print(f"  Teacher: {i}/{len(val_records)} evaluated", flush=True)

    print(f"Saved teacher predictions to {out_pred_path}")

def generate_local_model(model, tokenizer, prompt_text, max_new_tokens=60):
    inputs = tokenizer(prompt_text, return_tensors="pt")
    input_ids = inputs["input_ids"]
    attention_mask = inputs["attention_mask"]

    with torch.no_grad():
        out = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )

    # Decode only the newly generated tokens
    new_tokens = out[0][input_ids.shape[1]:]
    generated_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    # Extract JSON string up to the matching closing brace
    # If the text has a valid JSON start, take up to the first balanced closing brace or newline
    first_brace = generated_text.find("{")
    if first_brace != -1:
        brace_count = 0
        end_idx = -1
        for idx in range(first_brace, len(generated_text)):
            if generated_text[idx] == '{':
                brace_count += 1
            elif generated_text[idx] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = idx + 1
                    break
        if end_idx != -1:
            return generated_text[first_brace:end_idx]
        return generated_text[first_brace:]
    return generated_text

def evaluate_hf_model(model_path_or_name,
                      val_path="data/validation.jsonl",
                      out_pred_path="results/student_predictions.jsonl",
                      label="Model"):
    print("=" * 60)
    print(f"Evaluating {label} ({model_path_or_name})...")
    print("=" * 60)

    tokenizer = AutoTokenizer.from_pretrained(model_path_or_name, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(model_path_or_name, torch_dtype=torch.bfloat16, local_files_only=True)
    model.eval()

    with open(val_path, "r", encoding="utf-8") as f:
        val_records = [json.loads(line.strip()) for line in f if line.strip()]

    os.makedirs(os.path.dirname(out_pred_path) or ".", exist_ok=True)
    latencies = []
    with open(out_pred_path, "w", encoding="utf-8") as out_f:
        for i, rec in enumerate(val_records, 1):
            vid = rec["id"]
            cmd = rec["text"].strip()
            prompt = f"Command: {cmd}\nJSON:\n"

            t0 = time.time()
            raw_pred = generate_local_model(model, tokenizer, prompt)
            lat_ms = (time.time() - t0) * 1000.0
            latencies.append(lat_ms)

            pred_obj = {"id": vid, "prediction": raw_pred, "latency_ms": round(lat_ms, 2)}
            out_f.write(json.dumps(pred_obj, ensure_ascii=False) + "\n")
            out_f.flush()
            if i % 25 == 0 or i == len(val_records):
                print(f"  {label}: {i}/{len(val_records)} evaluated", flush=True)

    lat_sorted = sorted(latencies)
    p50 = lat_sorted[int(0.50 * len(lat_sorted))]
    p95 = lat_sorted[int(0.95 * len(lat_sorted))]
    print(f"{label} Latency: p50={p50:.2f}ms, p95={p95:.2f}ms")
    print(f"Saved {label} predictions to {out_pred_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher", action="store_true")
    parser.add_argument("--untrained", action="store_true")
    parser.add_argument("--student", action="store_true")
    parser.add_argument("--student-model", default="models/v1")
    args = parser.parse_args()

    if args.teacher:
        evaluate_teacher()
    if args.untrained:
        evaluate_hf_model("EleutherAI/pythia-70m", out_pred_path="results/untrained_predictions.jsonl", label="Untrained Pythia-70M")
    if args.student:
        evaluate_hf_model(args.student_model, out_pred_path="results/student_predictions.jsonl", label="Trained Student")
