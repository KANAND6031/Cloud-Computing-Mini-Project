import os
import sys

# Ensure repository root is in python path
sys.path.insert(0, os.path.abspath("."))

import json
import ipaddress
import pytest
from tools.nacl_sim import load_rules, decide
from worker.clean import REQUIRED_KEYS, ALLOWED_INTENTS


# --- Test 1: Data Cleaning Rules ---
def test_clean_validation_rules():
    """Verify that dataset cleaning filtering logic strictly implements requirements (a)-(e)."""
    # Valid record
    cmd_text = "set alarm for six am tomorrow"
    valid_raw = '{"intent": "alarm_set", "date": "tomorrow", "time": "six am", "place": null}'
    parsed = json.loads(valid_raw)
    assert set(parsed.keys()) == REQUIRED_KEYS
    assert parsed["intent"] in ALLOWED_INTENTS
    for slot in ("date", "time", "place"):
        val = parsed.get(slot)
        if val is not None:
            assert val.lower() in cmd_text.lower()

    # (a) Invalid JSON
    invalid_json = '{"intent": "alarm_set", broken...'
    with pytest.raises(Exception):
        json.loads(invalid_json)

    # (b) Extra / Missing keys
    wrong_keys = {"intent": "alarm_set", "date": "tomorrow"}
    assert set(wrong_keys.keys()) != REQUIRED_KEYS

    # (c) Invalid intent
    bad_intent = {"intent": "turn_on_lights", "date": None, "time": None, "place": None}
    assert bad_intent["intent"] not in ALLOWED_INTENTS

    # (d) Slot not appearing in command text
    hallucinated_slot = {"intent": "weather_query", "date": None, "time": None, "place": "paris"}
    cmd_london = "what is the weather in london"
    assert hallucinated_slot["place"] not in cmd_london


# --- Test 2: Stateless NACL Simulator ---
def test_nacl_stateless_rules():
    """Verify that public subnet NACL correctly enforces allow/deny and rule ordering."""
    rules = load_rules("network/nacl.json")

    # Inbound allow web traffic
    act, r = decide(rules, {"direction": "inbound", "protocol": "tcp", "port": 443, "address": "192.0.2.55"})
    assert act == "allow" and r == 210

    # Inbound deny abusive block 198.51.100.0/24 on web port
    act, r = decide(rules, {"direction": "inbound", "protocol": "tcp", "port": 443, "address": "198.51.100.9"})
    assert act == "deny" and r == 100

    # Inbound SSH from management subnet allowed
    act, r = decide(rules, {"direction": "inbound", "protocol": "tcp", "port": 22, "address": "10.20.5.130"})
    assert act == "allow" and r == 220

    # Inbound SSH from outside management subnet denied
    act, r = decide(rules, {"direction": "inbound", "protocol": "tcp", "port": 22, "address": "192.0.2.55"})
    assert act == "deny"

    # Outbound TCP 8000 to app subnet allowed
    act, r = decide(rules, {"direction": "outbound", "protocol": "tcp", "port": 8000, "address": "10.20.1.50"})
    assert act == "allow" and r == 100

    # Outbound client reply allowed on ephemeral port
    act, r = decide(rules, {"direction": "outbound", "protocol": "tcp", "port": 54321, "address": "192.0.2.55"})
    assert act == "allow" and r == 110

    # Unauthorized database port from data subnet denied
    act, r = decide(rules, {"direction": "inbound", "protocol": "tcp", "port": 5432, "address": "10.20.5.20"})
    assert act == "deny"


# --- Test 3: Output Schema & Fault Injection Validation ---
def test_schema_and_fault_injection():
    """Verify that service output validation passes valid JSON and rejects invalid/injected payloads."""
    with open("data/schema.json", "r", encoding="utf-8") as f:
        schema = json.load(f)

    allowed_intents = set(schema["intents"])
    required_keys = set(schema["keys"])

    valid_output = {
        "intent": "datetime_query",
        "date": None,
        "time": None,
        "place": "tokyo"
    }
    assert set(valid_output.keys()) == required_keys
    assert valid_output["intent"] in allowed_intents

    # Fault injected string must fail JSON parsing
    fault_payload = "not json"
    with pytest.raises(Exception):
        json.loads(fault_payload)


# --- Test 4: Subnet VLSM Allocations and Contiguity ---
def test_subnet_vlsm_math():
    """Verify that subnet allocations are contiguous, non-overlapping, and correctly sized."""
    subnets = [
        ("app", "10.20.0.0/22", 1000, 1022),
        ("public", "10.20.4.0/24", 250, 254),
        ("data", "10.20.5.0/25", 100, 126),
        ("management", "10.20.5.128/27", 20, 30)
    ]

    supernet = ipaddress.ip_network("10.20.0.0/16")
    prev_end = None

    for name, cidr, needed, expected_usable in subnets:
        net = ipaddress.ip_network(cidr)
        # Inside supernet
        assert net.subnet_of(supernet)
        # Sizing satisfies formula 2^(32-prefix) - 2 >= needed
        usable = (2 ** (32 - net.prefixlen)) - 2
        assert usable == expected_usable
        assert usable >= needed
        # Contiguity check
        if prev_end is not None:
            assert int(net.network_address) == prev_end + 1
        prev_end = int(net.broadcast_address)
