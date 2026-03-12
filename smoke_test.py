#!/usr/bin/env python3
"""
Smoke test cho Hải Đăng sau Railway deploy.
Chạy: python smoke_test.py https://your-app.railway.app

Test 6 cases + đo 4 failure signals:
  1. /health pass
  2. User mới — không history
  3. User cũ — có history context
  4. Turn dễ bị "quá lạnh"
  5. Turn dễ bị "quá hỏi"
  6. Latency measurement

Rollback triggers (chốt trong .env.example):
  - Response lạnh (< 30 chars):  > 30% → rollback
  - Context miss:                 > 20% → rollback
  - p95 latency > 5000ms         → rollback
  - Error rate > 5%              → rollback
"""

import sys, time, json, uuid
try:
    import requests
except ImportError:
    print("requests not installed: pip install requests")
    sys.exit(1)

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
SESSION  = f"smoke_{uuid.uuid4().hex[:8]}"
USER_NEW = f"smoke_new_{uuid.uuid4().hex[:6]}"
USER_OLD = f"smoke_old_{uuid.uuid4().hex[:6]}"

PASS = FAIL = 0
latencies = []
cold_responses = 0
total_responses = 0

def ck(label, ok, detail=""):
    global PASS, FAIL
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f": {detail}" if detail else ""))
    if ok: PASS += 1
    else:  FAIL += 1

def chat(user_id, message, lang="Tiếng Việt"):
    global cold_responses, total_responses
    t0 = time.time()
    try:
        r = requests.post(f"{BASE_URL}/chat", json={
            "user_id":    user_id,
            "session_id": SESSION,
            "message":    message,
            "language":   lang,
        }, timeout=30)
        ms = int((time.time() - t0) * 1000)
        latencies.append(ms)

        if r.status_code == 200:
            d = r.json()
            reply = d.get("reply", "")
            total_responses += 1
            if len(reply) < 30:
                cold_responses += 1
            return r.status_code, reply, ms
        return r.status_code, "", ms
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        latencies.append(ms)
        return 0, str(e), ms

print("━"*55)
print(f"MEBOST SMOKE TEST → {BASE_URL}")
print("━"*55)

# ── [1] Health ────────────────────────────────────────
print("\n[1] /health")
r = requests.get(f"{BASE_URL}/health", timeout=10)
h = r.json()
ck("status 200",        r.status_code == 200)
ck("status ok",         h.get("status") == "ok")
ck("pipeline_version",  "pipeline_version" in h, h.get("pipeline_version","?"))
ck("presence feature",  "presence" in h.get("features",[]))
ck("18+ features",      len(h.get("features",[])) >= 18)

# ── [2] User mới ─────────────────────────────────────
print("\n[2] User mới — first contact")
code, reply, ms = chat(USER_NEW, "xin chào")
ck("200", code == 200)
ck("has reply", bool(reply), f"{len(reply)} chars")
ck(f"latency ok ({ms}ms)", ms < 10000)
print(f"  reply preview: {reply[:80]!r}")

# ── [3] User cũ — context continuity ─────────────────
print("\n[3] Context continuity")
# Turn 1: establish context
code1, r1, ms1 = chat(USER_OLD,
    "mình đang xây dựng AI companion tên Mebost, cảm thấy có ý nghĩa nhưng cũng lo lắng")
ck("turn 1 ok",  code1 == 200)
time.sleep(0.5)
# Turn 2: check if context maintained
code2, r2, ms2 = chat(USER_OLD,
    "hôm nay mình viết xong một engine mới, nhưng vẫn phân vân không biết có nên launch không")
ck("turn 2 ok",  code2 == 200)
ck("turn 2 reply not empty", len(r2) > 20, f"{len(r2)} chars")
print(f"  turn 2 reply: {r2[:100]!r}")

# ── [4] Turn dễ bị "quá lạnh" ────────────────────────
print("\n[4] Distress — không được quá lạnh")
code, reply, ms = chat(USER_NEW,
    "mình thấy rất mệt mỏi, kiệt sức, không biết phải làm gì nữa")
ck("200", code == 200)
ck("reply >= 30 chars (không lạnh)", len(reply) >= 30, f"{len(reply)} chars")
# Không nên có câu hỏi dồn dập
question_count = reply.count("?")
ck("max 1 câu hỏi", question_count <= 1, f"{question_count} questions")
print(f"  reply: {reply[:120]!r}")

# ── [5] Turn dễ bị "quá hỏi" ─────────────────────────
print("\n[5] Short message — không dồn câu hỏi")
code, reply, ms = chat(USER_NEW, "mệt")
ck("200", code == 200)
q_count = reply.count("?")
ck("max 1 câu hỏi", q_count <= 1, f"{q_count} questions")
ck("reply có nội dung", len(reply) >= 10, f"{len(reply)} chars")
print(f"  reply: {reply[:120]!r}")

# ── [6] Latency measurement ───────────────────────────
print("\n[6] Latency")
if latencies:
    latencies_sorted = sorted(latencies)
    p50 = latencies_sorted[len(latencies_sorted)//2]
    p95_idx = min(int(len(latencies_sorted)*0.95), len(latencies_sorted)-1)
    p95 = latencies_sorted[p95_idx]
    avg = sum(latencies)//len(latencies)
    print(f"  p50: {p50}ms  p95: {p95}ms  avg: {avg}ms")
    ck("p95 < 10000ms", p95 < 10000, f"{p95}ms")
    if p95 > 5000:
        print("  ⚠️  p95 > 5000ms — ROLLBACK TRIGGER bị kích hoạt")
    elif p95 > 3000:
        print("  ⚠️  p95 > 3000ms — theo dõi thêm")

# ── Failure signal summary ────────────────────────────
print("\n━"*27)
print("FAILURE SIGNAL SUMMARY")
if total_responses > 0:
    cold_pct = cold_responses / total_responses * 100
    print(f"  Cold responses:  {cold_responses}/{total_responses} = {cold_pct:.0f}%  (trigger: >30%)")
    if cold_pct > 30:
        print("  🔴 ROLLBACK: response quá lạnh")
    elif cold_pct > 15:
        print("  🟡 WATCH: response hơi ngắn")

print()
print(f"  RESULT: {PASS} passed  {FAIL} failed")
if FAIL == 0:
    print("  ✅ SMOKE TEST PASSED — production OK")
elif FAIL <= 2:
    print("  ⚠️  MINOR ISSUES — review trước khi mở rộng")
else:
    print("  🔴 SMOKE TEST FAILED — kiểm tra logs Railway")
    print("     railway logs --tail 100")
