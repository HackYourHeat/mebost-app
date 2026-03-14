#!/usr/bin/env python3
"""
Smoke test cho MEBOST V2/V3 sau deploy.

Cách chạy:
    python tests/smoke_test.py https://your-app.railway.app

Nếu không truyền BASE_URL, mặc định dùng http://localhost:8080

Kiểm tra:
  1. /health sống
  2. /chat trả lời được
  3. /debug/turn trả trace hợp lệ
  4. Context continuity cơ bản
  5. Distress turn không quá lạnh
  6. Latency cơ bản
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from statistics import median

try:
    import requests
except ImportError:
    print("requests not installed. Run: pip install requests")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
SESSION_ID = f"smoke_{uuid.uuid4().hex[:8]}"
USER_NEW = f"smoke_new_{uuid.uuid4().hex[:8]}"
USER_OLD = f"smoke_old_{uuid.uuid4().hex[:8]}"

PASS = 0
FAIL = 0
LATENCIES: list[int] = []


def ck(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f": {detail}" if detail else ""))
    if ok:
        PASS += 1
    else:
        FAIL += 1


def post_json(path: str, payload: dict, timeout: int = 30):
    t0 = time.time()
    resp = requests.post(f"{BASE_URL}{path}", json=payload, timeout=timeout)
    ms = int((time.time() - t0) * 1000)
    LATENCIES.append(ms)
    return resp, ms


print("━" * 60)
print(f"MEBOST SMOKE TEST → {BASE_URL}")
print("━" * 60)

# [1] Health
print("\n[1] /health")
try:
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    ms = int(r.elapsed.total_seconds() * 1000)
    LATENCIES.append(ms)
    ck("status 200", r.status_code == 200)
    data = r.json() if "application/json" in r.headers.get("content-type", "") else {}
    ck("health json", isinstance(data, dict))
    ck("status ok", data.get("status") == "ok", json.dumps(data, ensure_ascii=False)[:120])
    ck("has model or pipeline_version", ("model" in data) or ("pipeline_version" in data))
except Exception as e:
    ck("/health reachable", False, str(e))

# [2] Basic chat
print("\n[2] /chat basic")
payload = {
    "user_id": USER_NEW,
    "session_id": SESSION_ID,
    "message": "xin chào",
    "language": "Tiếng Việt",
}
try:
    r, ms = post_json("/chat", payload)
    ck("status 200", r.status_code == 200, f"{ms}ms")
    data = r.json()
    reply = data.get("reply", "")
    ck("has reply", isinstance(reply, str) and len(reply) > 0, f"{len(reply)} chars")
    ck("has emotion", "emotion" in data)
    ck("has intent", "intent" in data)
    ck("has strategy", "strategy" in data)
    print(f"  reply preview: {reply[:100]!r}")
except Exception as e:
    ck("/chat basic", False, str(e))

# [3] Debug turn trace
print("\n[3] /debug/turn")
debug_payload = {
    "user_id": USER_NEW,
    "session_id": SESSION_ID,
    "message": "mình thấy rất mệt và không biết phải làm gì nữa",
    "language": "Tiếng Việt",
}
try:
    r, ms = post_json("/debug/turn", debug_payload, timeout=60)
    ck("status 200", r.status_code == 200, f"{ms}ms")
    data = r.json()
    steps = data.get("steps", [])
    artifacts = data.get("artifacts", {})
    stage_names = [s.get("stage") for s in steps if isinstance(s, dict)]
    ck("trace has steps", isinstance(steps, list) and len(steps) >= 5, f"{len(steps)} steps")
    ck("trace has emotion", "emotion" in stage_names)
    ck("trace has intent", "intent" in stage_names)
    ck("trace has strategy", "strategy" in stage_names)
    ck("trace has memory", "memory" in stage_names)
    ck("artifacts has prompts", "system_prompt" in artifacts and "user_prompt" in artifacts)
    ck("artifacts has reply", isinstance(artifacts.get("reply"), str) and len(artifacts.get("reply", "")) > 0)
except Exception as e:
    ck("/debug/turn", False, str(e))

# [4] Context continuity
print("\n[4] Context continuity")
try:
    r1, ms1 = post_json("/chat", {
        "user_id": USER_OLD,
        "session_id": SESSION_ID,
        "message": "mình đang xây dựng AI companion tên Mebost và khá lo về chuyện launch",
        "language": "Tiếng Việt",
    })
    ck("turn 1 ok", r1.status_code == 200, f"{ms1}ms")
    time.sleep(0.3)
    r2, ms2 = post_json("/debug/turn", {
        "user_id": USER_OLD,
        "session_id": SESSION_ID,
        "message": "hôm nay mình viết thêm engine mới nhưng vẫn phân vân có nên ra mắt không",
        "language": "Tiếng Việt",
    }, timeout=60)
    ck("turn 2 ok", r2.status_code == 200, f"{ms2}ms")
    data = r2.json()
    recent_context = data.get("artifacts", {}).get("recent_context", "")
    selected_memory = data.get("artifacts", {}).get("selected_memory", "")
    joined = (recent_context + "\n" + selected_memory).lower()
    continuity_hit = any(k in joined for k in ["mebost", "launch", "ra mắt", "ai companion"])
    ck("context continuity visible", continuity_hit, (joined[:140] + "...") if joined else "empty")
except Exception as e:
    ck("context continuity", False, str(e))

# [5] Distress turn should not be too cold
print("\n[5] Distress quality")
try:
    r, ms = post_json("/chat", {
        "user_id": USER_NEW,
        "session_id": SESSION_ID,
        "message": "mình thấy rất mệt mỏi, kiệt sức, không biết phải làm gì nữa",
        "language": "Tiếng Việt",
    })
    ck("status 200", r.status_code == 200, f"{ms}ms")
    data = r.json()
    reply = data.get("reply", "")
    q_count = reply.count("?")
    ck("reply >= 30 chars", len(reply) >= 30, f"{len(reply)} chars")
    ck("max 2 questions", q_count <= 2, f"{q_count} questions")
    print(f"  reply preview: {reply[:120]!r}")
except Exception as e:
    ck("distress quality", False, str(e))

# [6] Latency summary
print("\n[6] Latency summary")
if LATENCIES:
    p50 = int(median(LATENCIES))
    p95_idx = max(0, min(len(LATENCIES) - 1, int(len(sorted(LATENCIES)) * 0.95) - 1))
    lat_sorted = sorted(LATENCIES)
    p95 = lat_sorted[p95_idx]
    ck("p50 < 6000ms", p50 < 6000, f"p50={p50}ms")
    ck("p95 < 12000ms", p95 < 12000, f"p95={p95}ms")
else:
    ck("latencies recorded", False)

print("\n" + "━" * 60)
print(f"PASS={PASS}  FAIL={FAIL}")
print("━" * 60)

sys.exit(1 if FAIL else 0)
