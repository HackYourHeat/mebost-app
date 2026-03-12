from datetime import datetime, timezone, timedelta
from db import get_db, utc_now_iso

_GUEST_RETENTION_DAYS = 14

def _guest_expires_at() -> str:
    dt = datetime.now(timezone.utc) + timedelta(days=_GUEST_RETENTION_DAYS)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

# --------------------------------------------------
# User
# --------------------------------------------------

def ensure_user(user_id: str, language: str, display_name=None, device_hash=None):
    """Tạo user nếu chưa tồn tại, ngược lại update thông tin."""
    conn = get_db()
    cur  = conn.cursor()

    row = cur.execute(
        "SELECT user_id FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()

    if row is None:
        cur.execute(
            """INSERT INTO users
               (user_id, display_name, language, device_hash, memory_enabled,
                is_guest, guest_expires_at, created_at)
               VALUES (?, ?, ?, ?, 1, 1, ?, ?)""",
            (user_id, display_name, language, device_hash,
             _guest_expires_at(), utc_now_iso()),
        )
    else:
        if device_hash is not None:
            cur.execute(
                """UPDATE users
                   SET display_name = ?, language = ?, device_hash = ?
                   WHERE user_id = ?""",
                (display_name, language, device_hash, user_id),
            )
        else:
            cur.execute(
                """UPDATE users
                   SET display_name = ?, language = ?
                   WHERE user_id = ?""",
                (display_name, language, user_id),
            )

    conn.commit()
    conn.close()


# --------------------------------------------------
# Session
# --------------------------------------------------

def ensure_session(session_id: str, user_id: str, client_type: str):
    """Tạo session nếu chưa tồn tại."""
    conn = get_db()
    cur  = conn.cursor()

    row = cur.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()

    if row is None:
        cur.execute(
            """INSERT INTO sessions (session_id, user_id, client_type, created_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, user_id, client_type, utc_now_iso()),
        )

    conn.commit()
    conn.close()


# --------------------------------------------------
# Profile
# --------------------------------------------------

def get_user_profile(user_id: str) -> dict | None:
    """Load thông tin user. Trả None nếu không tồn tại."""
    conn = get_db()
    row  = conn.execute(
        """SELECT user_id, display_name, language, memory_enabled, created_at
           FROM users WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "user_id":        row["user_id"],
        "display_name":   row["display_name"],
        "language":       row["language"],
        "memory_enabled": row["memory_enabled"],
        "created_at":     row["created_at"],
    }


def get_user_sessions(user_id: str) -> list[dict]:
    """Lấy danh sách session của user, mới nhất trước."""
    conn = get_db()
    rows = conn.execute(
        """SELECT session_id, client_type, created_at
           FROM sessions WHERE user_id = ?
           ORDER BY created_at DESC""",
        (user_id,),
    ).fetchall()
    conn.close()

    return [
        {
            "session_id":  r["session_id"],
            "client_type": r["client_type"],
            "created_at":  r["created_at"],
        }
        for r in rows
    ]


def update_display_name(user_id: str, display_name: str):
    """Cập nhật tên hiển thị của user."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET display_name = ? WHERE user_id = ?",
        (display_name, user_id),
    )
    conn.commit()
    conn.close()
