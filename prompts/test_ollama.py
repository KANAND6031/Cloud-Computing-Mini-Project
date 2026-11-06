import json
import urllib.request
import time

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

test_commands = [
    "what alarms do i have set for today",
    "remove the upcoming calendar event",
    "need an alarm set for sunday at five in the morning",
    "give me the time at washington right now"
]

for cmd in test_commands:
    t0 = time.time()
    p = prompt_template.replace("{command}", cmd)
    req_data = json.dumps({
        "model": "phi3.5",
        "prompt": p,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0,
            "seed": 42,
            "num_predict": 60
        }
    }).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        print(f"Command: {cmd}")
        print(f"Time: {elapsed:.2f}s | Raw: {res['response'].strip()}")
        print("---")

