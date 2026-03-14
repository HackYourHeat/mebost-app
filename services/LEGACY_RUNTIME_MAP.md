# Gói 3 — Legacy / Experimental Runtime Map

Sau gói 3, **runtime chính** chỉ nên coi các file sau là authority:

- `app.py`
- `pipeline.py`
- `prompt_builder.py`
- `memory_engine.py`
- `memory_selector.py`
- `turn_trace_engine.py`
- `llm_adapter.py`
- `context_engine.py`
- `rate_limit_engine.py`
- `user_service.py`

## Runtime chính dùng gì

```text
message
→ emotion
→ intent
→ strategy (authority duy nhất)
→ save memory node
→ select memory node
→ build prompt
→ LLM
```

## Chuyển sang experimental / admin-only

Các file dưới đây **không nên nằm trong luồng chat chính** nữa ở bản production hiện tại:

- `memory_summary_engine.py`
- `memory_threading_engine.py`
- `life_graph_engine.py`
- `memory_extraction_engine.py`
- `memory_decay_engine.py`
- `response_policy.py`
- `response_policy_v2.py`
- `prompt_builder_backup.py`
- `prompt_arbiter.py`
- `presence_engine.py`
- `relational_continuity_engine.py`
- `familiarity_engine.py`
- `momentum_engine.py`
- `trust_engine.py`
- `user_state_engine.py`
- `internal_state_service.py`
- `personality_dna_engine.py`
- `pattern_learning_engine.py`
- `adaptive_tone_engine.py`
- `adaptive_personality_engine.py`
- `soul_dashboard.py`

## Vì sao

Các file trên không phải vô dụng. Nhưng ở trạng thái hiện tại:

- chúng làm prompt và decision bị chồng lớp
- khó debug lượt chat nào bị ai override
- khiến chất lượng thực tế kém ổn định hơn lý thuyết kiến trúc

## Quy tắc giữ kỷ luật runtime

1. Một lượt chat chỉ có **một authority quyết định strategy**.
2. Runtime chỉ dùng **một representation memory để prompt**: `memory_nodes`.
3. Bất kỳ engine mới nào muốn vào runtime chính phải trả lời được:
   - nó quyết định cái gì?
   - authority cũ có bị trùng không?
   - trace có nhìn ra vì sao nó thắng không?

## Khi nào đưa experimental quay lại runtime

Chỉ đưa lại khi có đủ 3 điều kiện:

- có trace rõ
- không trùng vai trò với authority hiện tại
- có test cho thấy nó tăng chất lượng thật sự
