"""
memory_engine.py — MEBOST Hải Đăng V2 (Clean)

Nguyên tắc mới:
- Lưu MỌI tin nhắn thực sự của user (không lọc theo score)
- Chỉ bỏ qua những phản hồi đơn lẻ vô nghĩa (ok, haha, 👍)
- Dedup chỉ khi text GIỐNG HỆT — không merge substring
- select_memory() chọn thông minh khi inject vào prompt
"""
from __future__ import annotations
import re
from db import get_db, utc_now_iso

MAX_MEMORY_TEXT   = 400   # ký tự tối đa mỗi node
MEMORY_FETCH_LIMIT = 60   # số node fetch để selector chọn

# ── Noise filter — chỉ những thứ thực sự trống rỗng ──────────────────────

_NOISE_PATTERNS = [
    r"^ok[\s!.]*$", r"^okay[\s!.]*$", r"^haha[\s!.]*$", r"^hi[\s!.]*$",
    r"^hello[\s!.]*$", r"^chào[\s!.]*$", r"^xin chào[\s!.]*$",
    r"^test[\s!.]*$", r"^cảm ơn[\s!.]*$", r"^thanks?[\s!.]*$",
    r"^thx[\s!.]*$", r"^ừ[\s!.]*$", r"^uh[\s!.]*$", r"^vâng[\s!.]*$",
    r"^đúng[\s!.]*$", r"^yeah[\s!.]*$", r"^yes[\s!.]*$", r"^no[\s!.]*$",
    r"^không[\s!.]*$", r"^k[\s!.]*$", r"^dc[\s!.]*$", r"^được[\s!.]*$",
    r"^👍+$", r"^😊+$", r"^\.\.\.*$",
]
_NOISE_RE = [re.compile(p, re.I) for p in _NOISE_PATTERNS]

def is_noise(text: str) -> bool:
    s = text.strip()
    if len(s) < 3:
        return True
    for pattern in _NOISE_RE:
        if pattern.match(s):
            return True
    return False

# ── Memory type classification ─────────────────────────────────────────────

_TYPE_RULES: list[tuple[list[str], str]] = [
    (["tên mình là", "my name is", "gọi mình là", "call me", "mình tên", "tôi tên"], "identity"),
    (["thích", "prefer", "yêu thích", "không thích", "do not like", "ghét"],          "preference"),
    (["mục tiêu", "goal", "muốn build", "muốn trở thành", "want to become",
      "ước mơ", "dream", "kế hoạch", "plan"],                                          "goal"),
    (["người yêu", "bạn gái", "bạn trai", "vợ", "chồng", "relationship",
      "bạn thân", "gia đình", "family", "bố", "mẹ", "anh", "chị", "em"],             "relationship"),
    (["lo", "sợ", "anxious", "worried", "mệt", "buồn", "tức", "angry",
      "cô đơn", "alone", "stress", "nặng lòng", "kiệt sức"],                         "emotional"),
    (["đừng", "không thích bị", "boundary", "please don't", "tôi không muốn"],        "boundary"),
    (["công việc", "nghề", "career", "job", "thất nghiệp", "unemployed",
      "học", "trường", "school", "dự án", "project"],                                 "life_context"),
]
_FALLBACK_TYPE = "general"

def classify_type(text: str) -> str:
    lower = text.lower()
    for keywords, mtype in _TYPE_RULES:
        if any(kw in lower for kw in keywords):
            return mtype
    return _FALLBACK_TYPE

# ── Core save ──────────────────────────────────────────────────────────────

def save_message_to_memory(
    user_id: str,
    source_message_id: int,
    text: str,
    importance_score: int,
) -> bool:
    """
    Lưu mọi tin nhắn thực sự của user vào memory_nodes.
    Chỉ bỏ qua noise thực sự (ok, haha, ...).
    Dedup chỉ khi text giống hệt nhau.
    """
    text = text.strip()
    if is_noise(text):
        return False

    memory_type = classify_type(text)
    memory_text = text[:MAX_MEMORY_TEXT]
    now = utc_now_iso()

    conn = get_db()

    # Chỉ dedup exact match — không merge substring
    existing = conn.execute(
        """SELECT id FROM memory_nodes
           WHERE user_id = ? AND memory_text = ? AND deleted_flag = 0
           LIMIT 1""",
        (user_id, memory_text),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE memory_nodes SET last_used_at = ?, updated_at = ? WHERE id = ?",
            (now, now, existing["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO memory_nodes
               (user_id, memory_type, memory_text, source_message_id,
                importance_score, status, created_at, updated_at, last_used_at, deleted_flag)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, 0)""",
            (user_id, memory_type, memory_text, source_message_id,
             importance_score, now, now, now),
        )

    conn.execute(
        "UPDATE messages SET memory_saved = 1 WHERE id = ?",
        (source_message_id,),
    )
    conn.commit()
    conn.close()
    return True

# ── Fetch for selector ─────────────────────────────────────────────────────

def get_memory_nodes(user_id: str, limit: int = MEMORY_FETCH_LIMIT) -> list[dict]:
    """Lấy memory nodes active, ưu tiên quan trọng và mới nhất."""
    conn = get_db()
    rows = conn.execute(
        """SELECT * FROM memory_nodes
           WHERE user_id = ? AND deleted_flag = 0 AND status = 'active'
           ORDER BY importance_score DESC, updated_at DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_memory_enabled(user_id: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT memory_enabled FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return bool(row["memory_enabled"]) if row else True

def clear_memory(user_id: str) -> int:
    """Xóa mềm toàn bộ memory của user."""
    conn = get_db()
    cur = conn.execute(
        "UPDATE memory_nodes SET deleted_flag = 1 WHERE user_id = ?", (user_id,)
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count
