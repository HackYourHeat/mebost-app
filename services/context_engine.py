from db import get_db

# --------------------------------------------------
# Constants
# --------------------------------------------------

MAX_CHARS_PER_MESSAGE = 240

ROLE_LABELS = {
    "user":      "User",
    "assistant": "Hai Dang",
}


# --------------------------------------------------
# Internal
# --------------------------------------------------

def get_recent_messages(session_id: str, limit: int = 3) -> list[dict]:
    """
    Lấy các message gần nhất trong session.
    - Bỏ deleted_by_user = 1
    - Lấy limit * 2 rows (mỗi turn = user + assistant)
    - Reverse để đọc xuôi thời gian
    """
    fetch_count = limit * 2

    conn = get_db()
    rows = conn.execute(
        """SELECT role, message_text
           FROM messages
           WHERE session_id = ?
             AND (deleted_by_user IS NULL OR deleted_by_user = 0)
           ORDER BY id DESC
           LIMIT ?""",
        (session_id, fetch_count),
    ).fetchall()
    conn.close()

    # Reverse: DB trả mới nhất trước, ta cần xuôi chiều
    return [{"role": r["role"], "message_text": r["message_text"]} for r in reversed(rows)]


def format_recent_context(rows: list[dict]) -> str:
    """
    Format list messages thành string context sạch.
    - role user → "User", assistant → "Hai Dang"
    - cắt tối đa MAX_CHARS_PER_MESSAGE ký tự mỗi dòng
    - bỏ row nếu message_text rỗng
    """
    lines = []

    for row in rows:
        text = (row.get("message_text") or "").strip()
        if not text:
            continue

        label = ROLE_LABELS.get(row.get("role", ""), "User")
        if len(text) > MAX_CHARS_PER_MESSAGE:
            text = text[:MAX_CHARS_PER_MESSAGE]

        lines.append(f"{label}: {text}")

    return "\n".join(lines)


# --------------------------------------------------
# Public API
# --------------------------------------------------

def get_recent_context(session_id: str, limit: int = 3) -> str:
    """
    Lấy và format recent context sẵn sàng inject vào prompt.

    Returns:
        str — context string, hoặc "" nếu không có dữ liệu
    """
    rows = get_recent_messages(session_id, limit)
    return format_recent_context(rows)
