#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time

import requests


def fail(msg: str, code: int = 1) -> None:
    print(f"[FAIL] {msg}")
    sys.exit(code)


def main() -> None:
    enabled = os.getenv("POST_DEPLOY_CHECK", "1").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        print("[SKIP] POST_DEPLOY_CHECK disabled")
        return

    base_url = os.getenv("POST_DEPLOY_BASE_URL", "").strip().rstrip("/")
    timeout = int(os.getenv("POST_DEPLOY_TIMEOUT", "20"))
    if not base_url:
        fail("POST_DEPLOY_BASE_URL is required")

    session_id = f"postdeploy_{int(time.time())}"
    user_id = f"postdeploy_user_{int(time.time())}"

    # 1. health
    r = requests.get(f"{base_url}/health", timeout=timeout)
    if r.status_code != 200:
        fail(f"/health returned {r.status_code}")
    health = r.json()
    if health.get("status") != "ok":
        fail(f"/health status not ok: {health}")
    print("[OK] /health")

    # 2. chat
    payload = {
        "user_id": user_id,
        "session_id": session_id,
        "message": "mình đang hơi mệt nhưng vẫn muốn tiếp tục xây dựng dự án này",
        "language": "Tiếng Việt",
    }
    r = requests.post(f"{base_url}/chat", json=payload, timeout=timeout)
    if r.status_code != 200:
        fail(f"/chat returned {r.status_code}: {r.text[:400]}")
    data = r.json()
    if not data.get("reply"):
        fail("/chat reply missing")
    print("[OK] /chat")

    # 3. debug turn
    payload["debug"] = True
    r = requests.post(f"{base_url}/debug/turn", json=payload, timeout=timeout)
    if r.status_code != 200:
        fail(f"/debug/turn returned {r.status_code}: {r.text[:400]}")
    debug = r.json()
    if "steps" not in debug:
        fail("/debug/turn missing steps")
    print("[OK] /debug/turn")

    print(json.dumps({
        "health": health,
        "chat_strategy": data.get("strategy"),
        "trace_steps": len(debug.get("steps", [])),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
