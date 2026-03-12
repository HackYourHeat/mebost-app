from db import get_db, utc_now_iso

# --------------------------------------------------
# Constants
# --------------------------------------------------

MEMORY_THRESHOLD     = 7
DEFAULT_CONFIDENCE   = 0.85
MAX_MEMORY_TEXT_CHARS = 300
SIMILAR_LOOKUP_LIMIT = 20

# --------------------------------------------------
# Signal sets for classify_memory_type
# --------------------------------------------------

_TYPE_RULES: list[tuple[list[str], str]] = [
    (["tên mình là", "my name is", "gọi mình là", "call me"],                          "identity"),
    (["thích", "prefer", "preference", "không thích", "do not like"],                  "preference"),
    (["mục tiêu", "goal", "muốn build", "want to build",
      "muốn trở thành", "want to become"],                                              "goal"),
    (["người yêu", "relationship", "bạn thân", "partner"],                             "relationship"),
    (["lo", "sợ", "anxious", "worried", "mệt", "buồn"],                               "emotional_pattern"),
    (["đừng", "không thích bị", "boundary"],                                           "boundary"),
    (["đang", "currently", "thất nghiệp", "unemployed", "gia đình", "family"],         "life_context"),
]

_FALLBACK_TYPE = "life_context"


# --------------------------------------------------
# 1. classify_memory_type
# --------------------------------------------------

def classify_memory_type(text: str) -> str:
    """Phân loại memory type dựa trên keyword matching."""
    lower = text.lower()
    for keywords, memory_type in _TYPE_RULES:
        if any(kw in lower for kw in keywords):
            return memory_type
    return _FALLBACK_TYPE


# --------------------------------------------------
# 2. build_memory_text
# --------------------------------------------------

def build_memory_text(text: str) -> str:
    """Strip và cắt memory text về tối đa MAX_MEMORY_TEXT_CHARS ký tự."""
    cleaned = text.strip()
    return cleaned[:MAX_MEMORY_TEXT_CHARS]


# --------------------------------------------------
# 3. similar_memory_exists
# --------------------------------------------------

def similar_memory_exists(user_id: str, memory_type: str, memory_text: str) -> dict | None:
    """
    Kiểm tra xem user đã có memory tương tự chưa.
    Dùng substring matching đơn giản.

    Returns:
        dict(row) nếu tìm thấy, None nếu không.
    """
    conn = get_db()
    rows = conn.execute(
        """SELECT *
           FROM memory_nodes
           WHERE user_id     = ?
             AND memory_type = ?
             AND deleted_flag = 0
           ORDER BY id DESC
           LIMIT ?""",
        (user_id, memory_type, SIMILAR_LOOKUP_LIMIT),
    ).fetchall()
    conn.close()

    new = memory_text.lower()
    for row in rows:
        old = (row["memory_text"] or "").lower()
        if old == new or old in new or new in old:
            return dict(row)

    return None


# --------------------------------------------------
# 4. update existing node
# --------------------------------------------------

def _update_memory_node(node_id: int, memory_text: str, importance_score: int) -> None:
    """Overwrite existing memory node với dữ liệu mới."""
    now  = utc_now_iso()
    conn = get_db()
    conn.execute(
        """UPDATE memory_nodes
           SET memory_text      = ?,
               importance_score = ?,
               confidence_score = ?,
               status           = 'active',
               updated_at       = ?,
               last_used_at     = ?
           WHERE id = ?""",
        (memory_text, importance_score, DEFAULT_CONFIDENCE, now, now, node_id),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------
# 5. create new node
# --------------------------------------------------

def _create_memory_node(
    user_id: str,
    memory_type: str,
    memory_text: str,
    source_message_id: int,
    importance_score: int,
) -> None:
    """Insert memory node mới vào DB + gán vào life thread."""
    now  = utc_now_iso()
    conn = get_db()
    cur  = conn.execute(
        """INSERT INTO memory_nodes
           (user_id, memory_type, memory_text, source_message_id,
            importance_score, confidence_score, status,
            created_at, updated_at, last_used_at, deleted_flag)
           VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, 0)""",
        (user_id, memory_type, memory_text, source_message_id,
         importance_score, DEFAULT_CONFIDENCE, now, now, now),
    )
    node_id = cur.lastrowid
    conn.commit()
    conn.close()
    # Threading (V2.2)
    try:
        from services.memory_threading_engine import assign_node_to_thread
        assign_node_to_thread(user_id, node_id, memory_text, importance_score)
    except Exception:
        pass


# --------------------------------------------------
# 6. mark message as saved
# --------------------------------------------------

def _mark_message_saved(source_message_id: int) -> None:
    """Đánh dấu message đã được lưu vào memory."""
    conn = get_db()
    conn.execute(
        "UPDATE messages SET memory_saved = 1 WHERE id = ?",
        (source_message_id,),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------
# 7. Public API
# --------------------------------------------------

def save_memory_node(
    user_id: str,
    source_message_id: int,
    text: str,
    importance_score: int,
) -> bool:
    """
    Pipeline chính: quyết định create/update memory node.

    Returns:
        True  — nếu đã save hoặc update memory
        False — nếu không đủ điều kiện
    """
    if importance_score < MEMORY_THRESHOLD:
        return False

    memory_type = classify_memory_type(text)
    memory_text = build_memory_text(text)

    existing = similar_memory_exists(user_id, memory_type, memory_text)

    if existing:
        _update_memory_node(existing["id"], memory_text, importance_score)
    else:
        _create_memory_node(user_id, memory_type, memory_text, source_message_id, importance_score)

    _mark_message_saved(source_message_id)
    return True
