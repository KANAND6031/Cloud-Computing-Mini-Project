import os
import sys
import json
import socket
import logging
import tarfile
import threading
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import jsonschema
import boto3
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("inference-service")

# Configuration from environment variables
MODEL_URI = os.environ.get("MODEL_URI", "s3://models/v1/model.tar.gz")
MODEL_VERSION = os.environ.get("MODEL_VERSION", "v1")
S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://127.0.0.1:8333")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "64"))
CACHE_DIR = os.environ.get("CACHE_DIR", "/tmp/model_cache")

# Pod / hostname for X-Served-By header
POD_NAME = os.environ.get("HOSTNAME") or socket.gethostname()

# Global state
is_ready = False
model = None
tokenizer = None
schema_data: Dict[str, Any] = {}

# Fallback schema if schema.json is missing
DEFAULT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "date", "time", "place"],
    "properties": {
        "intent": {
            "enum": [
                "alarm_set", "alarm_query", "calendar_set", "calendar_query",
                "calendar_remove", "weather_query", "datetime_query", "recommendation_events"
            ]
        },
        "date": {"type": ["string", "null"]},
        "time": {"type": ["string", "null"]},
        "place": {"type": ["string", "null"]}
    }
}

VALID_INTENTS = {
    "alarm_set", "alarm_query", "calendar_set", "calendar_query",
    "calendar_remove", "weather_query", "datetime_query", "recommendation_events"
}


def load_schema():
    global schema_data
    schema_paths = [
        "schema.json",
        os.path.join(os.path.dirname(__file__), "schema.json"),
        "data/schema.json",
        "/app/schema.json"
    ]
    for sp in schema_paths:
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    schema_data = json.load(f)
                    logger.info(f"Loaded schema from {sp}")
                    return
            except Exception as e:
                logger.warning(f"Failed to read schema from {sp}: {e}")
    logger.info("Using embedded default schema")
    schema_data = {"json_schema": DEFAULT_JSON_SCHEMA}


def download_model_from_s3(model_uri: str, s3_endpoint: str, target_dir: str) -> str:
    """Download model and tokenizer files from SeaweedFS S3."""
    logger.info(f"Preparing model from URI: {model_uri} using S3 endpoint: {s3_endpoint}")
    os.makedirs(target_dir, exist_ok=True)

    # Check if model files already exist locally (e.g. from previous run or mount)
    if os.path.exists(os.path.join(target_dir, "config.json")) and os.path.exists(os.path.join(target_dir, "model.safetensors")):
        logger.info(f"Model files already present in {target_dir}")
        return target_dir

    if model_uri.startswith("s3://"):
        uri_path = model_uri[5:]
        parts = uri_path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
    else:
        bucket = "models"
        prefix = model_uri.lstrip("/")

    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "any"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "any"),
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
    )

    clean_prefix = prefix.rstrip("/")

    # Strategy 1: Direct tar.gz key
    if clean_prefix.endswith(".tar.gz"):
        archive_path = os.path.join(target_dir, os.path.basename(clean_prefix))
        logger.info(f"Downloading archive s3://{bucket}/{clean_prefix}...")
        s3.download_file(bucket, clean_prefix, archive_path)
        logger.info("Extracting archive...")
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(path=target_dir)
        return target_dir

    # Strategy 2: Look for model.tar.gz under prefix candidates
    candidates = [
        f"{clean_prefix}/model.tar.gz",
        f"models/{clean_prefix}/model.tar.gz",
        f"{clean_prefix}/model-{MODEL_VERSION}.tar.gz",
        f"models/{clean_prefix}/model-{MODEL_VERSION}.tar.gz"
    ]
    for cand in candidates:
        try:
            s3.head_object(Bucket=bucket, Key=cand)
            archive_path = os.path.join(target_dir, "model.tar.gz")
            logger.info(f"Found archive at s3://{bucket}/{cand}, downloading...")
            s3.download_file(bucket, cand, archive_path)
            logger.info("Extracting archive...")
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(path=target_dir)
            return target_dir
        except Exception:
            continue

    # Strategy 3: Prefix download of individual files
    logger.info(f"Listing objects under prefix s3://{bucket}/{clean_prefix}...")
    paginator = s3.get_paginator("list_objects_v2")
    found_any = False
    for page in paginator.paginate(Bucket=bucket, Prefix=clean_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            rel_path = os.path.relpath(key, clean_prefix)
            if rel_path == "." or key.endswith("/"):
                continue
            dest_file = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            logger.info(f"Downloading s3://{bucket}/{key} -> {dest_file}...")
            s3.download_file(bucket, key, dest_file)
            found_any = True

    if not found_any:
        # Try with "models/" prefix
        alt_prefix = f"models/{clean_prefix}"
        for page in paginator.paginate(Bucket=bucket, Prefix=alt_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel_path = os.path.relpath(key, alt_prefix)
                if rel_path == "." or key.endswith("/"):
                    continue
                dest_file = os.path.join(target_dir, rel_path)
                os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                logger.info(f"Downloading s3://{bucket}/{key} -> {dest_file}...")
                s3.download_file(bucket, key, dest_file)
                found_any = True

    if not found_any:
        raise RuntimeError(f"Could not locate model artifacts in s3://{bucket}/{prefix}")

    return target_dir


def load_model_worker():
    global is_ready, model, tokenizer
    try:
        load_schema()
        target_dir = os.path.join(CACHE_DIR, MODEL_VERSION)
        download_model_from_s3(MODEL_URI, S3_ENDPOINT, target_dir)

        logger.info(f"Loading tokenizer and model from {target_dir}...")
        tok = AutoTokenizer.from_pretrained(target_dir, local_files_only=True)
        if tok.pad_token is None:
            tok.pad_token = tok.eos_token

        mod = AutoModelForCausalLM.from_pretrained(
            target_dir,
            torch_dtype=torch.bfloat16,
            local_files_only=True
        )
        mod.eval()

        tokenizer = tok
        model = mod
        is_ready = True
        logger.info(f"Model {MODEL_VERSION} successfully loaded. Service is ready on port 8000!")
    except Exception as e:
        logger.exception(f"Failed to load model: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spawn background thread to load model so server starts listening immediately
    thread = threading.Thread(target=load_model_worker, daemon=True)
    thread.start()
    yield


app = FastAPI(title="Command Parser Inference Service", lifespan=lifespan)


@app.middleware("http")
async def add_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Model-Version"] = MODEL_VERSION
    response.headers["X-Served-By"] = POD_NAME
    return response


class ParseRequest(BaseModel):
    text: str


def validate_output(raw_str: str) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Validate model output against schema requirements."""
    try:
        obj = json.loads(raw_str)
    except Exception:
        return False, None

    if not isinstance(obj, dict):
        return False, None

    # Must contain valid intent
    if "intent" not in obj or obj.get("intent") not in VALID_INTENTS:
        return False, None

    # Per Rule 3 of schema.json, if the command/model does not mention a slot, it is null
    for slot in ("date", "time", "place"):
        if slot not in obj:
            obj[slot] = None

    # Exactly four keys
    if set(obj.keys()) != {"intent", "date", "time", "place"}:
        return False, None

    # Slots must be string or None
    for slot in ("date", "time", "place"):
        val = obj.get(slot)
        if val is not None and not isinstance(val, str):
            return False, None

    # Json schema validation if available
    json_schema = schema_data.get("json_schema") or DEFAULT_JSON_SCHEMA
    try:
        jsonschema.validate(instance=obj, schema=json_schema)
    except Exception:
        return False, None

    return True, obj


def extract_json_candidate(text: str) -> str:
    """Extract substring from first { to matching balanced } if present."""
    first_brace = text.find("{")
    if first_brace == -1:
        return text.strip()
    brace_count = 0
    for idx in range(first_brace, len(text)):
        if text[idx] == "{":
            brace_count += 1
        elif text[idx] == "}":
            brace_count -= 1
            if brace_count == 0:
                return text[first_brace:idx + 1]
    return text[first_brace:].strip()


@app.get("/healthz")
def healthz():
    """Liveness probe: returns 200 as long as process is alive."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness probe: returns 503 until model is loaded, 200 after that."""
    if not is_ready:
        return JSONResponse(status_code=503, content={"status": "loading"})
    return {"status": "ready"}


@app.post("/parse")
def parse_command(req: ParseRequest):
    """Parse English command into 4-key JSON."""
    if not is_ready:
        return JSONResponse(status_code=503, content={"error": "model_not_ready"})

    # Prepare prompt matching student training format
    prompt = f"Command: {req.text.strip()}\nJSON:\n"
    inputs = tokenizer(prompt, return_tensors="pt")

    with torch.no_grad():
        out = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )

    # Decode newly generated tokens
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    generated_text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    candidate = extract_json_candidate(generated_text)

    # Fault injection: replace model output with "not json" before checking
    if os.environ.get("FAULT_INJECT", "0").strip() == "1":
        logger.info("FAULT_INJECT=1 active: replacing model output with 'not json'")
        candidate = "not json"

    # Validate output against schema.json
    valid, parsed_obj = validate_output(candidate)
    if not valid or parsed_obj is None:
        logger.warning(f"Invalid model output rejected: {candidate!r}")
        return JSONResponse(
            status_code=500,
            content={"error": "invalid_model_output"}
        )

    # Return exactly the 4-key JSON object
    return parsed_obj
