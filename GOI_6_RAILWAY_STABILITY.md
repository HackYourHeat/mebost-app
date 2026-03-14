# Gói 6 — Railway Production Stability

## Lưu vào đâu

- `services/runtime_guard.py` → lưu vào `services/`
- `scripts/post_deploy_check.py` → lưu vào `scripts/`
- `scripts/prune_sqlite_state.py` → lưu vào `scripts/`
- `tests/railway_production_test.py` → lưu vào `tests/`
- `railway.json` → thay file ở root project
- `.env.example` → thay file ở root project

## Mục tiêu

1. Sau deploy có thể tự kiểm tra `/health`, `/chat`, `/debug/turn`
2. LLM timeout / lỗi mạng không làm app vỡ flow
3. Trace debug không làm nặng runtime thường
4. SQLite local/volume được dọn gọn định kỳ
5. Có cờ env để bật tắt debug, cleanup, post-deploy checks

## Biến môi trường mới

- `ENABLE_DEBUG_TURN=1`
- `ENABLE_TRACE_IN_CHAT=0`
- `ENABLE_SQLITE_PRUNE=1`
- `SQLITE_PRUNE_DAYS=30`
- `POST_DEPLOY_CHECK=1`
- `POST_DEPLOY_BASE_URL=https://your-app.railway.app`
- `POST_DEPLOY_TIMEOUT=20`
