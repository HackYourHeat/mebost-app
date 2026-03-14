#!/usr/bin/env python3
"""
Kiểm tra hành vi pipeline ở mức integration thông qua /debug/turn.

Cách chạy:
    python tests/pipeline_integration_test.py https://your-app.railway.app
"""
from __future__ import annotations

import sys
import uuid

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"

CASES = [
    {
        "name": "help should guide",
        "message": "mình đang rất rối, mình nên làm gì bây giờ?",
        "expected_strategy": "guide",
    },
    {
        "name": "frustration should engage",
        "message": "bạn cứ hỏi mãi mà không giúp gì cả, trả lời thẳng đi",
        "expected_strategy": "engage",
    },
    {
        "name": "self attack should comfort or reframe",
        "message": "mình đúng là vô dụng và chẳng làm được gì ra hồn",
        "expected_strategy_any": ["comfort", "reframe"],
    },
    {
        "name": "simple vent should reflect",
        "message": "mình chỉ muốn tâm sự thôi, không cần giải pháp",
        "expected_strategy": "reflect",
    },
]


def fetch_strategy(message: str) -> str:
    payload = {
        "user_id": f"pi_{uuid.uuid4().hex[:8]}",
        "session_id": f"pi_s_{uuid.uuid4().hex[:8]}",
        "message": message,
        "language": "Tiếng Việt",
    }
    resp = requests.post(f"{BASE_URL}/debug/turn", json=payload, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"status={resp.status_code} body={resp.text[:200]}")
    data = resp.json()
    for step in data.get("steps", []):
        if step.get("stage") == "strategy":
            return str((step.get("value") or {}).get("strategy", ""))
    raise RuntimeError("strategy step not found")


failed = 0
for case in CASES:
    try:
        strategy = fetch_strategy(case["message"])
        if "expected_strategy" in case:
            ok = strategy == case["expected_strategy"]
            detail = f"got={strategy}, expected={case['expected_strategy']}"
        else:
            ok = strategy in case["expected_strategy_any"]
            detail = f"got={strategy}, expected_any={case['expected_strategy_any']}"
        print(("✓" if ok else "✗"), case["name"], "—", detail)
        if not ok:
            failed += 1
    except Exception as e:
        print("✗", case["name"], "—", str(e))
        failed += 1

sys.exit(1 if failed else 0)
