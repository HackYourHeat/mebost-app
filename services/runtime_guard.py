from __future__ import annotations

import os
from typing import Any


_TRUE_SET = {"1", "true", "yes", "on"}


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUE_SET


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def is_production_env() -> bool:
    return bool(
        os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_PROJECT_ID")
        or str(os.getenv("FLASK_ENV", "")).strip().lower() == "production"
        or str(os.getenv("APP_ENV", "")).strip().lower() == "production"
    )


def is_debug_turn_enabled() -> bool:
    # Local/dev: bật mặc định. Production: tắt mặc định.
    return env_flag("ENABLE_DEBUG_TURN", default=not is_production_env())


def is_trace_in_chat_enabled() -> bool:
    # Trace trong /chat nên luôn off mặc định ở production.
    return env_flag("ENABLE_TRACE_IN_CHAT", default=False)


def redact_prompts_in_trace() -> bool:
    # Production nên ẩn prompt đầy đủ theo mặc định.
    return env_flag("REDACT_DEBUG_PROMPTS", default=is_production_env())


def trace_max_chars() -> int:
    return env_int("TRACE_MAX_CHARS", 1600 if is_production_env() else 3000)


def is_sqlite_prune_enabled() -> bool:
    return env_flag("ENABLE_SQLITE_PRUNE", default=True)


def sqlite_prune_days() -> int:
    return env_int("SQLITE_PRUNE_DAYS", 30)


def should_expose_trace(debug_requested: bool) -> bool:
    if debug_requested:
        return is_trace_in_chat_enabled() or is_debug_turn_enabled()
    return is_trace_in_chat_enabled()


def should_allow_debug_route() -> bool:
    return is_debug_turn_enabled()


def _truncate(value: Any, max_chars: int) -> Any:
    if not isinstance(value, str):
        return value
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "..."


def safe_trace_payload(trace: dict[str, Any]) -> dict[str, Any]:
    """Giữ trace hữu ích nhưng không quá nặng hoặc quá lộ prompt ở production."""
    if not trace:
        return {}

    artifacts = dict(trace.get("artifacts") or {})
    max_chars = trace_max_chars()

    # Luôn giữ các artifact hữu ích nhưng cắt ngắn.
    kept_keys = [
        "selected_memory",
        "recent_context",
        "reply",
        "response_time_ms",
        "memory_trace",
        "memory_runtime_snapshot",
    ]

    if not redact_prompts_in_trace():
        kept_keys.extend(["system_prompt", "user_prompt"])

    filtered: dict[str, Any] = {}
    for key in kept_keys:
        if key in artifacts:
            filtered[key] = _truncate(artifacts[key], max_chars)

    return {
        "user_id": trace.get("user_id", ""),
        "session_id": trace.get("session_id", ""),
        "message": _truncate(trace.get("message", ""), max_chars),
        "language": trace.get("language", ""),
        "steps": trace.get("steps", []),
        "artifacts": filtered,
    }
