# MEBOST — Testing Guide (Gói 5)

## Lưu các file này vào đâu

Đặt đúng như sau:

```text
mebost-ai/
├─ TESTING.md
├─ tests/
│  ├─ smoke_test.py
│  ├─ debug_turn_test.py
│  ├─ pipeline_integration_test.py
│  └─ memory_runtime_test.py
└─ scripts/
   └─ runtime_audit.py
```

`tests/` dùng cho test.

`scripts/` dùng cho audit và tool dev.

**Không đặt các file này trong `services/`.**

---

## 1. Chạy audit repo trước

```bash
python scripts/runtime_audit.py .
```

Audit này kiểm tra:

- file runtime lõi có tồn tại không
- app có `/debug/turn` không
- `pipeline.py` có `select_strategy_with_reason` không
- có import nhầm `legacy` không

---

## 2. Chạy smoke test

Local:

```bash
python tests/smoke_test.py
```

Railway / production:

```bash
python tests/smoke_test.py https://your-app.railway.app
```

Smoke test kiểm tra:

- `/health`
- `/chat`
- `/debug/turn`
- context continuity cơ bản
- distress turn không quá lạnh
- latency cơ bản

---

## 3. Chạy test riêng cho debug trace

```bash
python tests/debug_turn_test.py https://your-app.railway.app
```

Dùng để kiểm tra endpoint `/debug/turn` có trả:

- steps
- artifacts
- system_prompt
- user_prompt
- reply
- response_time_ms

---

## 4. Chạy integration test cho strategy

```bash
python tests/pipeline_integration_test.py https://your-app.railway.app
```

Case chính:

- help → guide
- frustration → engage
- self attack → comfort/reframe
- vent → reflect

---

## 5. Chạy memory runtime test

```bash
python tests/memory_runtime_test.py https://your-app.railway.app
```

Test này kiểm tra:

- message có nghĩa được lưu vào memory
- noise không làm memory phình vô ích
- selected memory giữ được context cũ

---

## 6. Thứ tự nên chạy sau mỗi deploy

```bash
python scripts/runtime_audit.py .
python tests/smoke_test.py https://your-app.railway.app
python tests/debug_turn_test.py https://your-app.railway.app
python tests/pipeline_integration_test.py https://your-app.railway.app
python tests/memory_runtime_test.py https://your-app.railway.app
```

---

## 7. Khi nào coi là deploy ổn

Deploy ổn khi:

- runtime audit pass
- smoke test pass
- debug turn pass
- integration strategy pass
- memory runtime pass

Nếu smoke pass nhưng debug turn fail, nghĩa là app còn sống nhưng observability đang hỏng.

Nếu debug turn pass nhưng strategy test fail, nghĩa là pipeline còn chạy nhưng rule chọn hành vi đang lệch.

Nếu memory runtime fail, nghĩa là continuity của Hải Đăng sẽ yếu dần dù chat vẫn trả lời được.
