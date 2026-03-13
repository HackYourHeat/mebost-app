# --------------------------------------------------
# Temporal Self Engine — MEBOST Hải Đăng V1.9
# --------------------------------------------------
# Hải Đăng biết thời gian đã trôi qua giữa các cuộc trò chuyện.
# Không tạo bảng mới — đọc từ messages table đã có.
#
# Output:
#   time_gap_minutes    — phút kể từ message cuối
#   relationship_days   — ngày kể từ message đầu tiên
#   session_continuity  — continuous | pause | return | first_time
# --------------------------------------------------

from __future__ import annotations
from datetime import datetime, timezone

from db import get_db

# --------------------------------------------------
# Thresholds
# --------------------------------------------------
_GAP_CONTINUOUS_MAX =   5   # phút
_GAP_PAUSE_MAX      = 360   # 6 giờ
_GAP_DAY_MAX        = 1440  # 24 giờ


def compute_temporal_context(user_id: str) -> dict:
    """
    Đọc timestamps từ messages table → tính time_gap, relationship_age,
    session_continuity.

    Trả về dict an toàn — không raise nếu DB trống.
    """
    now = datetime.now(timezone.utc)

    try:
        db = get_db()

        # Last message timestamp (bất kỳ role)
        last_row = db.execute(
            """SELECT created_at FROM messages
               WHERE user_id = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id,),
        ).fetchone()

        # First message timestamp
        first_row = db.execute(
            """SELECT created_at FROM messages
               WHERE user_id = ?
               ORDER BY id ASC LIMIT 1""",
            (user_id,),
        ).fetchone()

        db.close()
    except Exception:
        return _default_context()

    if not last_row or not last_row["created_at"]:
        return _default_context()

    # Parse timestamps
    last_ts  = _parse_ts(last_row["created_at"])
    first_ts = _parse_ts(first_row["created_at"]) if first_row else last_ts

    if last_ts is None:
        return _default_context()

    gap_minutes       = (now - last_ts).total_seconds() / 60
    relationship_days = (now - first_ts).days if first_ts else 0

    continuity = _classify_gap(gap_minutes)

    return {
        "time_gap_minutes":  round(gap_minutes, 1),
        "relationship_days": relationship_days,
        "session_continuity": continuity,
    }


def temporal_prompt_hint(ctx: dict) -> str:
    """Chuyển temporal context → hướng dẫn ngắn cho prompt."""
    cont = ctx.get("session_continuity", "first_time")
    days = ctx.get("relationship_days", 0)
    gap  = ctx.get("time_gap_minutes", 0)

    if cont == "first_time":
        return "Đây là lần đầu user chat — tiếp cận nhẹ nhàng, không đề cập ký ức cũ."

    if cont == "continuous":
        return "Cuộc trò chuyện đang tiếp diễn — tiếp tục mạch tự nhiên, không cần mở đầu lại."

    if cont == "pause":
        h = round(gap / 60, 1)
        return "User vừa quay lại — kết nối lại nhẹ nhàng, có thể nhắc lại chủ đề trước."

    if cont == "return":
        if days >= 7:
            return (
                "User quay lại sau một thời gian — chào đón ấm áp, hỏi thăm nhẹ trước khi đi vào chủ đề cũ."
                "hỏi nhẹ về thời gian vừa qua trước khi đi vào chủ đề sâu."
            )
        return "User quay lại sau hơn 1 ngày — kết nối lại trước, không nhảy vào chủ đề cũ ngay."

    return ""


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _classify_gap(gap_minutes: float) -> str:
    if gap_minutes < _GAP_CONTINUOUS_MAX:
        return "continuous"
    if gap_minutes < _GAP_PAUSE_MAX:
        return "pause"
    if gap_minutes < _GAP_DAY_MAX:
        return "return"
    return "return"


def _parse_ts(ts_str: str) -> datetime | None:
    if not ts_str:
        return None
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _default_context() -> dict:
    return {
        "time_gap_minutes":  0.0,
        "relationship_days": 0,
        "session_continuity": "first_time",
    }
