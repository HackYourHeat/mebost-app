# --------------------------------------------------
# Logging Engine — MEBOST Hải Đăng V1.3
# --------------------------------------------------
# Hai tầng log:
#   1. logs/mebost.log          — log tổng hệ thống (file, skip trên Railway)
#   2. logs/users/<user_id>.log — nhật ký riêng từng user
#   3. stdout                   — luôn bật, Railway View Logs đọc từ đây
#
# Railway mode: khi RAILWAY_ENVIRONMENT có mặt, bỏ file handler,
# chỉ stream ra stdout với format đẹp có emoji.
# --------------------------------------------------

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

# --------------------------------------------------
# Paths
# --------------------------------------------------

_BASE    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR  = os.path.join(_BASE, "logs")
USER_DIR = os.path.join(LOG_DIR, "users")
LOG_FILE = os.path.join(LOG_DIR, "mebost.log")

os.makedirs(LOG_DIR,  exist_ok=True)
os.makedirs(USER_DIR, exist_ok=True)

# --------------------------------------------------
# Detect môi trường
# --------------------------------------------------

# Railway tự inject RAILWAY_ENVIRONMENT (production/staging)
_ON_RAILWAY = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"))
_LOG_LEVEL  = os.environ.get("LOG_LEVEL", "INFO").upper()

# --------------------------------------------------
# Format
# --------------------------------------------------

# File / plain format
_FMT     = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATEFMT = "%Y-%m-%dT%H:%M:%S"

# Railway console format — dùng emoji theo level để dễ lọc trên View Logs
_EMOJI = {
    "DEBUG":    "🔍",
    "INFO":     "🌊",
    "WARNING":  "⚠️ ",
    "ERROR":    "🔴",
    "CRITICAL": "🚨",
}

class _RailwayFormatter(logging.Formatter):
    """Format có emoji prefix — dễ đọc trên Railway View Logs."""
    def format(self, record: logging.LogRecord) -> str:
        emoji = _EMOJI.get(record.levelname, "  ")
        base  = super().format(record)
        return f"{emoji} {base}"

# --------------------------------------------------
# Cache — tránh duplicate handlers
# --------------------------------------------------

_user_loggers: dict[str, logging.Logger] = {}

# --------------------------------------------------
# Setup global logger
# --------------------------------------------------

def setup_logging() -> None:
    """
    Khởi tạo logger tổng hệ thống.

    - Trên Railway: chỉ stdout (Railway thu thập từ stdout/stderr).
    - Local: stdout + file rotate 5MB × 3.

    LOG_LEVEL env var kiểm soát mức log (mặc định INFO).
    """
    root = logging.getLogger("mebost")
    if root.handlers:
        return  # đã setup rồi

    level = getattr(logging, _LOG_LEVEL, logging.INFO)
    root.setLevel(level)

    plain_fmt   = logging.Formatter(_FMT, datefmt=_DATEFMT)
    railway_fmt = _RailwayFormatter(_FMT, datefmt=_DATEFMT)

    # ── Stdout — luôn bật ──────────────────────────
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(railway_fmt if _ON_RAILWAY else plain_fmt)
    sh.setLevel(level)
    root.addHandler(sh)

    # ── File — chỉ khi KHÔNG chạy trên Railway ─────
    if not _ON_RAILWAY:
        try:
            fh = RotatingFileHandler(
                LOG_FILE, maxBytes=5 * 1024 * 1024,
                backupCount=3, encoding="utf-8",
            )
            fh.setFormatter(plain_fmt)
            fh.setLevel(level)
            root.addHandler(fh)
        except Exception as exc:
            print(f"[logging_engine] file handler fail: {exc}", file=sys.stderr)

    root.info(
        "LOGGING_INIT  env=%s level=%s file=%s",
        "railway" if _ON_RAILWAY else "local",
        _LOG_LEVEL,
        "disabled" if _ON_RAILWAY else LOG_FILE,
    )


# Khởi tạo ngay khi import
setup_logging()
logger = logging.getLogger("mebost")


# --------------------------------------------------
# Per-user logger
# --------------------------------------------------

def _safe_user_id(user_id: str) -> str:
    """
    Sanitize user_id để tránh path injection.
    Chỉ giữ chữ, số, _ và -.
    Ví dụ: "u/../../x" → "user_unknown"
    """
    safe = re.sub(r"[^\w\-]", "", user_id)
    return safe[:64] if safe else "user_unknown"


def get_user_logger(user_id: str) -> logging.Logger:
    """
    Trả về logger riêng cho user_id.
    - Local: tạo file logs/users/<safe_user_id>.log  (rotate 2MB × 3)
    - Railway: chỉ propagate lên logger tổng (stdout), không ghi file.
    Cached để không tạo duplicate handlers.
    """
    safe = _safe_user_id(user_id)

    if safe in _user_loggers:
        return _user_loggers[safe]

    ulog = logging.getLogger(f"mebost.user.{safe}")
    if ulog.handlers:
        _user_loggers[safe] = ulog
        return ulog

    ulog.setLevel(logging.INFO)
    ulog.propagate = True   # luôn đẩy lên log tổng → stdout

    if not _ON_RAILWAY:
        formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)
        log_path  = os.path.join(USER_DIR, f"{safe}.log")
        try:
            fh = RotatingFileHandler(
                log_path, maxBytes=2 * 1024 * 1024,
                backupCount=3, encoding="utf-8",
            )
            fh.setFormatter(formatter)
            ulog.addHandler(fh)
        except Exception as exc:
            logger.warning("user_logger_init_fail user=%s error=%s", safe, exc)

    _user_loggers[safe] = ulog
    return ulog


# --------------------------------------------------
# System-level helpers (dùng logger tổng)
# --------------------------------------------------

def log_chat_start(user_id: str, session_id: str, message: str) -> None:
    logger.info(
        "CHAT_START  user=%s session=%s msg_len=%d",
        user_id, session_id, len(message),
    )


def log_llm_call(model: str, latency_ms: int) -> None:
    logger.info("LLM_CALL    model=%s latency=%dms", model, latency_ms)


def log_llm_error(model: str, error: str) -> None:
    logger.error("LLM_ERROR   model=%s error=%s", model, error)


def log_chat_done(
    user_id: str, session_id: str,
    latency_ms: int, emotion: str, intent: str,
) -> None:
    logger.info(
        "CHAT_DONE   user=%s session=%s latency=%dms emotion=%s intent=%s",
        user_id, session_id, latency_ms, emotion, intent,
    )


def log_memory_saved(user_id: str, memory_type: str, score: int) -> None:
    logger.info("MEMORY_SAVE user=%s type=%s score=%d", user_id, memory_type, score)


def log_memory_decay(
    user_id: str, node_id: int, old_score: int, new_score: int,
) -> None:
    logger.info(
        "MEMORY_DECAY user=%s node=%d %d→%d",
        user_id, node_id, old_score, new_score,
    )


def log_memory_clear(user_id: str) -> None:
    logger.info("MEMORY_CLEAR user=%s", user_id)


def log_rate_limit_hit(user_id: str, used: int, limit: int) -> None:
    logger.warning("RATE_LIMIT  user=%s used=%d limit=%d", user_id, used, limit)


def log_exception(route: str, error: Exception) -> None:
    logger.exception("EXCEPTION   route=%s error=%s", route, error)


# --------------------------------------------------
# Per-user event helpers
# --------------------------------------------------

def ulog_request(
    user_id: str,
    session_id: str,
    language: str,
    client_type: str,
    message: str,
) -> None:
    """Log request đầu pipeline vào user log."""
    ulog = get_user_logger(user_id)
    preview = message[:80].replace("\n", " ")
    ulog.info(
        "REQUEST  session=%s lang=%s client=%s msg_len=%d preview=%r",
        session_id, language, client_type, len(message), preview,
    )


def ulog_analysis(
    user_id: str,
    emotion: str,
    intensity: int,
    intent: str,
    importance: int,
    policy_mode: str,
) -> None:
    """Log kết quả phân tích vào user log."""
    ulog = get_user_logger(user_id)
    ulog.info(
        "ANALYSIS emotion=%s(%d) intent=%s importance=%d policy=%s",
        emotion, intensity, intent, importance, policy_mode,
    )


def ulog_memory(
    user_id: str,
    memory_saved: bool,
    has_summary: bool,
) -> None:
    """Log trạng thái memory vào user log."""
    ulog = get_user_logger(user_id)
    ulog.info(
        "MEMORY   saved=%s has_summary=%s",
        memory_saved, has_summary,
    )


def ulog_response(
    user_id: str,
    latency_ms: int,
    reply_len: int,
) -> None:
    """Log response đã gửi vào user log."""
    ulog = get_user_logger(user_id)
    ulog.info(
        "RESPONSE latency=%dms reply_len=%d",
        latency_ms, reply_len,
    )


def ulog_llm_error(user_id: str, error: str) -> None:
    """Log LLM error vào cả log tổng lẫn user log."""
    log_llm_error("openrouter", error)
    ulog = get_user_logger(user_id)
    ulog.error("LLM_ERROR %s", error)


def ulog_memory_action(
    user_id: str,
    action: str,
    target_id: int | None = None,
) -> None:
    """Log memory action (forget / clear / toggle) vào user log."""
    ulog = get_user_logger(user_id)
    if target_id is not None:
        ulog.info("MEMORY_ACTION action=%s target_id=%d", action, target_id)
    else:
        ulog.info("MEMORY_ACTION action=%s", action)
