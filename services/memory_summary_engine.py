from db import get_db, utc_now_iso

# --------------------------------------------------
# Constants
# --------------------------------------------------

DEFAULT_NODE_LIMIT   = 8
MAX_CHARS_PER_LINE   = 120


# --------------------------------------------------
# 1. get_active_memory_nodes
# --------------------------------------------------

def get_active_memory_nodes(user_id: str, limit: int = DEFAULT_NODE_LIMIT) -> list[dict]:
    """Lấy memory nodes còn active, ưu tiên quan trọng và mới nhất."""
    conn = get_db()
    rows = conn.execute(
        """SELECT *
           FROM memory_nodes
           WHERE user_id     = ?
             AND deleted_flag = 0
           ORDER BY importance_score DESC, updated_at DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --------------------------------------------------
# 2. build_memory_summary_text
# --------------------------------------------------

def build_memory_summary_text(rows: list[dict]) -> str:
    """
    Chuyển list memory nodes thành summary text ngắn gọn.
    Mỗi dòng: "- {memory_text[:120]}"
    """
    if not rows:
        return ""

    lines = []
    for row in rows[:DEFAULT_NODE_LIMIT]:
        text = (row.get("memory_text") or "").strip()
        if not text:
            continue
        lines.append(f"- {text[:MAX_CHARS_PER_LINE]}")

    return "\n".join(lines)


# --------------------------------------------------
# 3. get_next_summary_version
# --------------------------------------------------

def get_next_summary_version(user_id: str) -> int:
    """Trả về version tiếp theo cho memory summary của user."""
    conn = get_db()
    row  = conn.execute(
        "SELECT MAX(summary_version) FROM memory_summaries WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()

    current = row[0] if row and row[0] is not None else 0
    return current + 1


# --------------------------------------------------
# 4. deactivate_old_summaries
# --------------------------------------------------

def deactivate_old_summaries(user_id: str) -> None:
    """Đặt toàn bộ summary cũ của user về is_active = 0."""
    conn = get_db()
    conn.execute(
        "UPDATE memory_summaries SET is_active = 0 WHERE user_id = ?",
        (user_id,),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------
# 5 & 6. insert summary row
# --------------------------------------------------

def _insert_summary(
    user_id: str,
    summary_text: str,
    version: int,
    source_count: int,
) -> None:
    """Insert summary mới vào memory_summaries."""
    conn = get_db()
    conn.execute(
        """INSERT INTO memory_summaries
           (user_id, summary_text, summary_version, source_memory_count, created_at, is_active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (user_id, summary_text, version, source_count, utc_now_iso()),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------
# 7. update intent_state cache
# --------------------------------------------------

def _cache_summary_in_intent_state(user_id: str, summary_text: str) -> None:
    """Upsert memory_summary vào intent_state để dễ truy xuất nhanh."""
    now  = utc_now_iso()
    conn = get_db()
    conn.execute(
        """INSERT INTO intent_state (user_id, memory_summary, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               memory_summary = excluded.memory_summary,
               updated_at     = excluded.updated_at""",
        (user_id, summary_text, now),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------
# 5. save_memory_summary  (public entry point)
# --------------------------------------------------

def save_memory_summary(user_id: str) -> str:
    """
    Pipeline chính: build + lưu memory summary cho user.

    FIX: So sánh content với summary hiện tại trước khi rebuild.
    Chỉ insert version mới nếu content thật sự thay đổi.
    Tránh version nhảy liên tục khi memory không đổi.

    Returns:
        summary_text — có thể là "" nếu không có node nào
    """
    rows         = get_active_memory_nodes(user_id, limit=DEFAULT_NODE_LIMIT)
    summary_text = build_memory_summary_text(rows)
    source_count = len(rows)

    # Guard: bỏ qua nếu summary không thay đổi
    current = get_active_memory_summary(user_id)
    if current.strip() == summary_text.strip():
        return summary_text   # không rebuild vô ích

    deactivate_old_summaries(user_id)
    version = get_next_summary_version(user_id)

    _insert_summary(user_id, summary_text, version, source_count)
    _cache_summary_in_intent_state(user_id, summary_text)

    return summary_text


# --------------------------------------------------
# 8. get_active_memory_summary
# --------------------------------------------------

def get_active_memory_summary(user_id: str) -> str:
    """
    Lấy summary active hiện tại của user.

    Returns:
        summary_text hoặc "" nếu chưa có
    """
    conn = get_db()
    row  = conn.execute(
        """SELECT summary_text
           FROM memory_summaries
           WHERE user_id  = ?
             AND is_active = 1
           ORDER BY id DESC
           LIMIT 1""",
        (user_id,),
    ).fetchone()
    conn.close()

    return (row["summary_text"] or "") if row else ""
