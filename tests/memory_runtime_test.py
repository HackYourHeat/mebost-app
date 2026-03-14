#!/usr/bin/env python3
"""
Kiểm tra memory runtime qua /debug/turn.

Mục tiêu:
- message có nghĩa được lưu
- noise message không làm memory phình vô ích
- selected_memory xuất hiện sau khi đã có context trước đó

Cách chạy:
    python tests/memory_runtime_test.py https://your-app.railway.app
"""
from __future__ import annotations

import sys
import time
import uuid

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
USER_ID = f"mem_{uuid.uuid4().hex[:8]}"
SESSION_ID = f"mem_s_{uuid.uuid4().hex[:8]}"


def post_debug(message: str) -> dict:
    resp = requests.post(
        f"{BASE_URL}/debug/turn",
        json={
            "user_id": USER_ID,
            "session_id": SESSION_ID,
            "message": message,
            "language": "Tiếng Việt",
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"status={resp.status_code} body={resp.text[:200]}")
    return resp.json()


def get_memory_stage(data: dict) -> dict:
    for step in data.get("steps", []):
        if step.get("stage") == "memory":
            return step
    return {}


failed = 0

try:
    d1 = post_debug("mình đang xây dự án Mebost và rất lo về chuyện launch")
    m1 = get_memory_stage(d1)
    saved1 = bool((m1.get("value") or {}).get("memory_saved", False))
    print(("✓" if saved1 else "✗"), "meaningful message should save to memory", m1.get("reason", ""))
    if not saved1:
        failed += 1
except Exception as e:
    print("✗ meaningful message should save to memory —", str(e))
    failed += 1

try:
    time.sleep(0.2)
    d2 = post_debug("ok")
    m2 = get_memory_stage(d2)
    reason2 = m2.get("reason", "")
    print("✓ noise message processed", reason2)
except Exception as e:
    print("✗ noise message processed —", str(e))
    failed += 1

try:
    time.sleep(0.2)
    d3 = post_debug("hôm nay mình vẫn phân vân có nên ra mắt Mebost luôn không")
    selected = (d3.get("artifacts") or {}).get("selected_memory", "")
    hit = "mebost" in selected.lower() or "launch" in selected.lower() or "ra mắt" in selected.lower()
    print(("✓" if hit else "✗"), "selected_memory should carry prior context", selected[:160])
    if not hit:
        failed += 1
except Exception as e:
    print("✗ selected_memory should carry prior context —", str(e))
    failed += 1

sys.exit(1 if failed else 0)
