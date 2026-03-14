#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import time

import requests

BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BASE_URL", "http://localhost:8080")).rstrip("/")


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "OK" if ok else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(1)


def main() -> None:
    user_id = f"railway_test_user_{int(time.time())}"
    session_id = f"railway_test_session_{int(time.time())}"

    r = requests.get(f"{BASE_URL}/health", timeout=20)
    check("health 200", r.status_code == 200, str(r.status_code))
    health = r.json()
    check("health status ok", health.get("status") == "ok", str(health))
    check("pipeline version present", "pipeline_version" in health, str(health))

    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "message": "mình đang rối nhưng vẫn muốn tiếp tục làm cho hải đăng tốt hơn",
        "language": "Tiếng Việt",
    }
    r = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
    check("chat 200", r.status_code == 200, str(r.status_code))
    data = r.json()
    check("chat reply exists", bool(data.get("reply")), str(data)[:200])
    check("chat strategy exists", bool(data.get("strategy")), str(data))

    payload["debug"] = True
    r = requests.post(f"{BASE_URL}/debug/turn", json=payload, timeout=30)
    check("debug turn 200", r.status_code == 200, str(r.status_code))
    trace = r.json()
    check("trace has steps", isinstance(trace.get("steps"), list) and len(trace["steps"]) >= 4, str(trace)[:400])

    step_names = {s.get("stage") for s in trace.get("steps", [])}
    for required in ["emotion", "intent", "importance", "strategy", "memory"]:
        check(f"trace has {required}", required in step_names, str(step_names))


if __name__ == "__main__":
    main()
