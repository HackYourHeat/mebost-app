# Gói 6.1 — Runtime Guard Integration

## Lưu vào đâu

- `app.py` → **root project**
- `services/runtime_guard.py` → **services/**
- `GOI_6_1_RUNTIME_GUARD.md` → **root project**

## Mục tiêu

- Tắt `/debug/turn` ở production theo env
- Chỉ trả trace trong `/chat` khi env cho phép
- Cắt gọn trace để không quá nặng
- Ẩn prompt trong trace ở production theo mặc định

## Biến môi trường mới

- `ENABLE_DEBUG_TURN`
- `ENABLE_TRACE_IN_CHAT`
- `REDACT_DEBUG_PROMPTS`
- `TRACE_MAX_CHARS`

## Hành vi mặc định

### Local/dev
- `/debug/turn` bật
- `/chat` không trả trace trừ khi bạn bật `ENABLE_TRACE_IN_CHAT=true`
- prompt không bị ẩn trong trace trừ khi bạn tự bật redact

### Production / Railway
- `/debug/turn` tắt mặc định
- `/chat` không trả trace mặc định
- prompt bị ẩn khỏi trace mặc định
- trace bị cắt ngắn hơn

## Ví dụ env production an toàn

```env
ENABLE_DEBUG_TURN=false
ENABLE_TRACE_IN_CHAT=false
REDACT_DEBUG_PROMPTS=true
TRACE_MAX_CHARS=1600
```

## Ví dụ env staging/debug

```env
ENABLE_DEBUG_TURN=true
ENABLE_TRACE_IN_CHAT=true
REDACT_DEBUG_PROMPTS=false
TRACE_MAX_CHARS=3000
```
