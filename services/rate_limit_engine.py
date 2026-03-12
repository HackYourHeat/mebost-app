from datetime import datetime, timezone

from db import get_db, utc_now_iso

# --------------------------------------------------
# Config
# --------------------------------------------------

RATE_LIMIT_PER_MINUTE = 12


# --------------------------------------------------
# Time helpers
# --------------------------------------------------

def now_ts() -> int:
    """Trả về unix timestamp hiện tại (UTC)."""
    return int(datetime.now(timezone.utc).timestamp())


def parse_iso_to_ts(iso_str: str) -> int:
    """
    Parse ISO timestamp string → unix timestamp int.
    Trả về 0 nếu rỗng hoặc lỗi.
    """
    if not iso_str:
        return 0
    try:
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


# --------------------------------------------------
# Rate limit
# --------------------------------------------------

def check_rate_limit(user_id: str) -> tuple[bool, int]:
    """
    Kiểm tra rate limit trong cửa sổ 60 giây.

    Returns:
        (allowed, used_count)
        - allowed = False nếu đã đạt RATE_LIMIT_PER_MINUTE
        - used_count = số request đã dùng trong window
    """
    current_ts      = now_ts()
    window_start_ts = current_ts - 60

    conn = get_db()
    cur  = conn.cursor()

    # Lấy toàn bộ row của user, mới nhất trước
    rows = cur.execute(
        "SELECT id, created_at FROM rate_limits WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()

    valid_ids = []
    stale_ids = []

    for row in rows:
        ts = parse_iso_to_ts(row["created_at"])
        if ts >= window_start_ts:
            valid_ids.append(row["id"])
        else:
            stale_ids.append(row["id"])

    # Xóa các row cũ để giữ bảng gọn
    if stale_ids:
        cur.execute(
            f"DELETE FROM rate_limits WHERE id IN ({','.join('?' * len(stale_ids))})",
            stale_ids,
        )

    if len(valid_ids) >= RATE_LIMIT_PER_MINUTE:
        conn.commit()
        conn.close()
        return (False, len(valid_ids))

    # Cho phép: ghi nhận request mới
    cur.execute(
        "INSERT INTO rate_limits (user_id, created_at) VALUES (?, ?)",
        (user_id, utc_now_iso()),
    )

    conn.commit()
    conn.close()
    return (True, len(valid_ids) + 1)
