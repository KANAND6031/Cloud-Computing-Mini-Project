import json
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor

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

def call_ollama(cmd):
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
    t0 = time.time()
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=req_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - t0
        return cmd, res["response"].strip(), elapsed

commands = [
    "do i have any meetings scheduled the weekend after next",
    "i need a reminder at two hundred every day to check on my mother",
    "remind me of the meeting on tuesday",
    "is my calendar free for thursday",
    "do i have meeting with steve this week",
    "what is the forecast for tomorrow in chicago",
    "wake me up at six am tomorrow",
    "show me events in new york tonight",
    "cancel my dentist appointment on friday",
    "what time is it in paris"
]

t_start = time.time()
with ThreadPoolExecutor(max_workers=4) as ex:
    results = list(ex.map(call_ollama, commands))

total_time = time.time() - t_start
print(f"Total time for 10 commands with 4 workers: {total_time:.2f}s ({total_time/10:.2f}s per command)")
for c, r, el in results[:3]:
    print(f"[{el:.2f}s] {c} -> {r}")
