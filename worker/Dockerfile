FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir boto3

COPY worker/worker.py /app/worker/worker.py
COPY prompts/teacher_prompt.txt /app/prompts/teacher_prompt.txt
COPY data/commands_pool.jsonl /app/data/commands_pool.jsonl

ENV PYTHONUNBUFFERED=1
ENV PROMPT_FILE=/app/prompts/teacher_prompt.txt
ENV DATA_FILE=/app/data/commands_pool.jsonl
ENV OUTPUT_DIR=/app/shards

ENTRYPOINT ["python", "/app/worker/worker.py"]
