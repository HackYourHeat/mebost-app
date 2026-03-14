#!/usr/bin/env python3
"""
Kiểm tra riêng endpoint /debug/turn.

Cách chạy:
    python tests/debug_turn_test.py https://your-app.railway.app
"""
from __future__ import annotations

import json
import sys
import uuid

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
USER_ID = f"dbg_{uuid.uuid4().hex[:8]}"
SESSION_ID = f"dbg_s_{uuid.uuid4().hex[:8]}"


def assert_true(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"✓ {name}" + (f": {detail}" if detail else ""))
        return
    print(f"✗ {name}" + (f": {detail}" if detail else ""))
    sys.exit(1)


payload = {
    "user_id": USER_ID,
    "session_id": SESSION_ID,
    "message": "mình thấy rất mệt và đang phân vân có nên tiếp tục dự án này không",
    "language": "Tiếng Việt",
}

resp = requests.post(f"{BASE_URL}/debug/turn", json=payload, timeout=60)
assert_true("status 200", resp.status_code == 200, f"status={resp.status_code}")

data = resp.json()
steps = data.get("steps")
artifacts = data.get("artifacts")

assert_true("steps is list", isinstance(steps, list), type(steps).__name__)
assert_true("artifacts is dict", isinstance(artifacts, dict), type(artifacts).__name__)

required_steps = {"emotion", "intent", "importance", "trust", "pronoun", "strategy", "memory"}
actual_steps = {s.get("stage") for s in steps if isinstance(s, dict)}
missing = sorted(required_steps - actual_steps)
assert_true("required steps present", not missing, f"missing={missing}")

assert_true("system_prompt exists", isinstance(artifacts.get("system_prompt"), str) and len(artifacts.get("system_prompt", "")) > 20)
assert_true("user_prompt exists", isinstance(artifacts.get("user_prompt"), str) and len(artifacts.get("user_prompt", "")) > 5)
assert_true("reply exists", isinstance(artifacts.get("reply"), str) and len(artifacts.get("reply", "")) > 0)
assert_true("response_time_ms exists", isinstance(artifacts.get("response_time_ms"), int))

memory_trace = artifacts.get("memory_trace")
if memory_trace is not None:
    assert_true("memory_trace is dict when present", isinstance(memory_trace, dict))

print("\nDebug turn payload preview:")
print(json.dumps({
    "steps": steps[:3],
    "strategy": next((s for s in steps if s.get("stage") == "strategy"), {}),
    "artifacts_keys": sorted(list(artifacts.keys()))[:20],
}, ensure_ascii=False, indent=2)[:1600])
