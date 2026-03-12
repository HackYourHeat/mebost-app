from db import get_db, utc_now_iso
from services.memory_summary_engine import save_memory_summary


# --------------------------------------------------
# 1. get_memory_enabled
# --------------------------------------------------

def get_memory_enabled(user_id: str) -> bool:
    """Trả về trạng thái memory của user. Mặc định True nếu chưa có row."""
    conn = get_db()
    row  = conn.execute(
        "SELECT memory_enabled FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()

    if row is None:
        return True
    return bool(row["memory_enabled"])


# --------------------------------------------------
# 2. set_memory_enabled
# --------------------------------------------------

def set_memory_enabled(user_id: str, enabled: bool) -> bool:
    """
    Bật / tắt memory cho user.
    Cập nhật cả users và intent_state.
    """
    value = 1 if enabled else 0
    now   = utc_now_iso()
    conn  = get_db()

    conn.execute(
        "UPDATE users SET memory_enabled = ? WHERE user_id = ?",
        (value, user_id),
    )

    conn.execute(
        """INSERT INTO intent_state (user_id, memory_enabled, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
               memory_enabled = excluded.memory_enabled,
               updated_at     = excluded.updated_at""",
        (user_id, value, now),
    )

    conn.commit()
    conn.close()
    return enabled


# --------------------------------------------------
# 3. forget_message
# --------------------------------------------------

def forget_message(user_id: str, message_id: int) -> bool:
    """
    Đánh dấu message và memory node liên quan là đã quên.
    Rebuild summary sau đó.
    """
    now  = utc_now_iso()
    conn = get_db()

    # Soft-delete message
    conn.execute(
        """UPDATE messages
           SET deleted_by_user    = 1,
               is_memory_candidate = 0,
               memory_saved        = 0
           WHERE id = ? AND user_id = ?""",
        (message_id, user_id),
    )

    # Soft-delete memory nodes từ message này
    conn.execute(
        """UPDATE memory_nodes
           SET deleted_flag = 1,
               status       = 'forgotten',
               updated_at   = ?
           WHERE source_message_id = ? AND user_id = ?""",
        (now, message_id, user_id),
    )

    conn.commit()
    conn.close()

    save_memory_summary(user_id)
    return True


# --------------------------------------------------
# 4. clear_memory
# --------------------------------------------------

def clear_memory(user_id: str) -> bool:
    """
    Xóa toàn bộ ký ức của user.
    Rebuild summary (sẽ là "" vì không còn node nào).
    """
    now  = utc_now_iso()
    conn = get_db()

    # Soft-delete toàn bộ memory nodes
    conn.execute(
        """UPDATE memory_nodes
           SET deleted_flag = 1,
               status       = 'forgotten',
               updated_at   = ?
           WHERE user_id = ?""",
        (now, user_id),
    )

    # Deactivate toàn bộ summaries
    conn.execute(
        "UPDATE memory_summaries SET is_active = 0 WHERE user_id = ?",
        (user_id,),
    )

    conn.commit()
    conn.close()

    reset_memory_summary_cache(user_id)
    save_memory_summary(user_id)
    return True


# --------------------------------------------------
# 5. reset_memory_summary_cache
# --------------------------------------------------

def reset_memory_summary_cache(user_id: str) -> None:
    """Clear intent_state.memory_summary về chuỗi rỗng."""
    now  = utc_now_iso()
    conn = get_db()
    conn.execute(
        """INSERT INTO intent_state (user_id, memory_summary, updated_at)
           VALUES (?, '', ?)
           ON CONFLICT(user_id) DO UPDATE SET
               memory_summary = '',
               updated_at     = excluded.updated_at""",
        (user_id, now),
    )
    conn.commit()
    conn.close()
