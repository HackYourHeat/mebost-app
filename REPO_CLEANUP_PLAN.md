# Full gói 4 — Repo cleanup cho production

Mục tiêu của gói này là làm codebase **dễ hiểu, dễ sửa, ít chồng chéo**.

## 1. Runtime production chính thức

Chỉ các file sau được phép nằm trên luồng chat chính:

- `app.py`
- `db.py`
- `llm_adapter.py`
- `logging_engine.py`
- `rate_limit_engine.py`
- `user_service.py`
- `pipeline.py`
- `prompt_builder.py`
- `memory_engine.py`
- `memory_selector.py`
- `turn_trace_engine.py`

## 2. File giữ lại nhưng không chạy trong main flow

Các file sau chuyển sang `legacy/` hoặc `experimental/`:

### legacy/

- `response_policy.py`
- `response_policy_v2.py`
- `response_strategy_engine.py` (nếu vẫn chỉ còn compat shim thì có thể giữ ở root thêm 1–2 vòng deploy)
- `prompt_builder_backup.py`
- `pronoun_engine.py`
- `trust_engine.py`
- `user_state_engine.py`
- `internal_state_service.py`
- `presence_engine.py`
- `relational_continuity_engine.py`
- `temporal_self_engine.py`
- `familiarity_engine.py`
- `adaptive_tone_engine.py`
- `adaptive_personality_engine.py`
- `personality_dna_engine.py`
- `biological_engine.py`
- `consciousness_engine.py`
- `conversation_gravity_engine.py`
- `conversation_state_engine.py`
- `feedback_engine.py`
- `analytics_engine.py`
- `soul_dashboard.py`
- `memory_summary_engine.py`
- `memory_threading_engine.py`
- `memory_decay_engine.py`
- `memory_extraction_engine.py`
- `life_graph_engine.py`
- `listening_style_service.py`
- `memory_control_engine.py`
- `pattern_learning_engine.py`
- `momentum_engine.py`

### experimental/

Những file bạn vẫn muốn thử nghiệm độc lập thì chuyển sang `experimental/` thay vì để lẫn trong root.

## 3. Quy tắc import mới

Trong runtime production:

- `app.py` chỉ import từ đúng các file runtime chính thức.
- Không import chéo từ `legacy/`.
- Nếu cần giữ backward compatibility tạm thời, chỉ dùng shim 1 chiều và phải có TODO xóa.

## 4. Quy tắc review trước mỗi commit

Trước khi merge, kiểm 5 câu này:

1. File này có nằm trong runtime chính không?
2. Nó có đang quyết định cùng một thứ với file khác không?
3. Nó có được `/debug/turn` nhìn thấy không?
4. Nó có làm prompt dài và tự mâu thuẫn hơn không?
5. Bỏ file này đi thì chất lượng có giảm thật không?

Nếu không trả lời chắc được, file đó không nên ở main flow.

## 5. Cây repo production đề xuất

```text
.
├── app.py
├── db.py
├── llm_adapter.py
├── logging_engine.py
├── rate_limit_engine.py
├── user_service.py
├── pipeline.py
├── prompt_builder.py
├── memory_engine.py
├── memory_selector.py
├── turn_trace_engine.py
├── legacy/
├── experimental/
├── scripts/
└── docs/
```

## 6. Chiến lược migrate an toàn

### Phase A — khóa runtime
- Chốt `RUNTIME_MANIFEST.json`
- Chạy smoke test
- Deploy

### Phase B — di chuyển file
- Move file sang `legacy/`
- Giữ shim tạm nếu cần
- Chạy smoke test
- Deploy

### Phase C — xóa import chết
- grep toàn repo các import từ file cũ
- bỏ shim
- deploy lại

## 7. Điều không nên làm tiếp

- Không thêm engine mới vào root
- Không thêm prompt block mới nếu chưa trace được tác dụng
- Không để 2 file cùng quyết định depth / strategy / policy

## 8. Định nghĩa “production sạch”

Production sạch nghĩa là:

- một pipeline duy nhất
- một authority quyết định phản hồi
- một prompt builder duy nhất
- một runtime memory duy nhất
- một trace nhìn ra toàn bộ quyết định

