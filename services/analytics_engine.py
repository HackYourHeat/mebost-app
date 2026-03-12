# --------------------------------------------------
# Analytics Engine — MEBOST V1.3
# --------------------------------------------------
# Ghi file analytics JSON định kỳ:
#   logs/analytics/emotion_stats.json
#   logs/analytics/tone_distribution.json
#   logs/analytics/daily_usage.json
#
# Gọi flush_analytics() sau mỗi N chat hoặc theo cron.
# --------------------------------------------------

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from db import get_db

_BASE          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANALYTICS_DIR  = os.path.join(_BASE, "logs", "analytics")
os.makedirs(ANALYTICS_DIR, exist_ok=True)

_EMOTION_FILE  = os.path.join(ANALYTICS_DIR, "emotion_stats.json")
_TONE_FILE     = os.path.join(ANALYTICS_DIR, "tone_distribution.json")
_USAGE_FILE    = os.path.join(ANALYTICS_DIR, "daily_usage.json")


def _write_json(path: str, data: object) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def flush_emotion_stats() -> None:
    """Aggregate emotion counts từ emotion_logs."""
    try:
        db   = get_db()
        rows = db.execute(
            "SELECT emotion, COUNT(*) as cnt FROM emotion_logs GROUP BY emotion"
        ).fetchall()
        db.close()
        stats = {r["emotion"]: r["cnt"] for r in rows}
        stats["_updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(_EMOTION_FILE, stats)
    except Exception:
        pass


def flush_tone_distribution() -> None:
    """Snapshot tone profile distribution."""
    try:
        db   = get_db()
        rows = db.execute(
            "SELECT reply_length, reflection_level, warmth_level FROM user_tone_profile"
        ).fetchall()
        db.close()
        dist: dict[str, dict[str, int]] = {
            "reply_length":     {},
            "reflection_level": {},
            "warmth_level":     {},
        }
        for r in rows:
            for field in dist:
                val = r[field] or "medium"
                dist[field][val] = dist[field].get(val, 0) + 1
        dist["_updated_at"] = datetime.now(timezone.utc).isoformat()  # type: ignore[assignment]
        _write_json(_TONE_FILE, dist)
    except Exception:
        pass


def flush_daily_usage() -> None:
    """Đếm messages theo ngày."""
    try:
        db   = get_db()
        rows = db.execute(
            """SELECT substr(timestamp, 1, 10) as day, COUNT(*) as cnt
               FROM messages WHERE role='user'
               GROUP BY day ORDER BY day DESC LIMIT 30"""
        ).fetchall()
        db.close()
        usage = {r["day"]: r["cnt"] for r in rows}
        usage["_updated_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(_USAGE_FILE, usage)
    except Exception:
        pass


def flush_analytics() -> None:
    """Gọi toàn bộ flush functions."""
    flush_emotion_stats()
    flush_tone_distribution()
    flush_daily_usage()
