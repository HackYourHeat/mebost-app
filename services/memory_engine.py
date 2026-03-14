"""
memory_engine.py — MEBOST Hải Đăng V3.0 (Runtime Slim)

Mục tiêu:
- runtime chính chỉ dùng memory_nodes + memory_selector
- bỏ phụ thuộc runtime vào summary / thread / life graph
- trace được rõ: lưu hay không lưu, vì sao

Nguyên tắc:
- lưu hầu hết message có nghĩa
- chỉ bỏ noise thật sự
- dedup exact-match, không merge thông minh
- memory type chỉ để hỗ trợ selector, không điều khiển hành vi
"""
from __future__ import annotations

import re
from typing import Any

from db import get_db, utc_now_iso

MAX_MEMORY_TEXT = 400
MEMORY_FETCH_LIMIT = 60

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

_TYPE_RULES: list[tuple[list[str], str]] = [
    (["tên mình là", "my name is", "gọi mình là", "call me", "mình tên", "tôi tên"], "identity"),
    (["thích", "prefer", "yêu thích", "không thích", "do not like", "ghét"], "preference"),
    (["mục tiêu", "goal", "muốn build", "muốn trở thành", "want to become", "ước mơ", "dream", "kế hoạch", "plan"], "goal"),
    (["người yêu", "bạn gái", "bạn trai", "vợ", "chồng", "relationship", "bạn thân", "gia đình", "family", "bố", "mẹ", "anh", "chị", "em"], "relationship"),
    (["lo", "sợ", "anxious", "worried", "mệt", "buồn", "tức", "angry", "cô đơn", "alone", "stress", "nặng lòng", "kiệt sức"], "emotional"),
    (["đừng", "không thích bị", "boundary", "please don't", "tôi không muốn"], "boundary"),
    (["công việc", "nghề", "career", "job", "thất nghiệp", "unemployed", "học", "trường", "school", "dự án", "project"], "life_context"),
]
_FALLBACK_TYPE = "general"


def is_noise(text: str) -> bool:
    s = text.strip()
    if len(s) < 3:
        return True
    return any(p.match(s) for p in _NOISE_RE)


def classify_type(text: str) -> str:
    lower = text.lower()
    for keywords, memory_type in _TYPE_RULES:
        if any(kw in lower for kw in keywords):
            return memory_type
    return _FALLBACK_TYPE


def get_memory_enabled(user_id: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT memory_enabled FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return bool(row["memory_enabled"]) if row else True


def save_message_to_memory(
    user_id: str,
    source_message_id: int,
    text: str,
    importance_score: int,
) -> bool:
    saved, _, _ = save_message_to_memory_with_reason(user_id, source_message_id, text, importance_score)
    return saved


def save_message_to_memory_with_reason(
    user_id: str,
    source_message_id: int,
    text: str,
    importance_score: int,
) -> tuple[bool, str, int | None]:
    """
    Returns:
        (saved, reason, node_id)

    saved=True cả khi exact duplicate được refresh, vì runtime vẫn có memory hữu ích.
    """
    clean_text = text.strip()
    if is_noise(clean_text):
        return False, "noise_message_skipped", None

    memory_type = classify_type(clean_text)
    memory_text = clean_text[:MAX_MEMORY_TEXT]
    now = utc_now_iso()

    conn = get_db()
    existing = conn.execute(
        """SELECT id FROM memory_nodes
           WHERE user_id = ? AND memory_text = ? AND deleted_flag = 0
           LIMIT 1""",
        (user_id, memory_text),
    ).fetchone()

    node_id: int | None = None
    reason = "inserted_new_memory"

    if existing:
        node_id = int(existing["id"])
        conn.execute(
            "UPDATE memory_nodes SET last_used_at = ?, updated_at = ? WHERE id = ?",
            (now, now, node_id),
        )
        reason = "exact_duplicate_refreshed"
    else:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO memory_nodes
               (user_id, memory_type, memory_text, source_message_id,
                importance_score, status, created_at, updated_at, last_used_at, deleted_flag)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, 0)""",
            (user_id, memory_type, memory_text, source_message_id, importance_score, now, now, now),
        )
        node_id = cur.lastrowid

    conn.execute(
        "UPDATE messages SET memory_saved = 1 WHERE id = ?",
        (source_message_id,),
    )
    conn.commit()
    conn.close()
    return True, f"{reason} type={memory_type}", node_id


def get_memory_nodes(user_id: str, limit: int = MEMORY_FETCH_LIMIT) -> list[dict[str, Any]]:
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


def clear_memory(user_id: str) -> int:
    conn = get_db()
    cur = conn.execute(
        "UPDATE memory_nodes SET deleted_flag = 1, status = 'forgotten', updated_at = ? WHERE user_id = ?",
        (utc_now_iso(), user_id),
    )
    count = cur.rowcount
    conn.commit()
    conn.close()
    return count


def get_memory_runtime_snapshot(user_id: str) -> dict[str, Any]:
    """
    Snapshot gọn cho debug/runtime; không dùng summary/thread/graph.
    """
    try:
        conn = get_db()
        total_row = conn.execute(
            "SELECT COUNT(*) FROM memory_nodes WHERE user_id = ? AND deleted_flag = 0 AND status = 'active'",
            (user_id,),
        ).fetchone()
        type_rows = conn.execute(
            """SELECT memory_type, COUNT(*) AS cnt
               FROM memory_nodes
               WHERE user_id = ? AND deleted_flag = 0 AND status = 'active'
               GROUP BY memory_type ORDER BY cnt DESC""",
            (user_id,),
        ).fetchall()
        recent_rows = conn.execute(
            """SELECT id, memory_type, memory_text, importance_score, updated_at
               FROM memory_nodes
               WHERE user_id = ? AND deleted_flag = 0 AND status = 'active'
               ORDER BY updated_at DESC LIMIT 10""",
            (user_id,),
        ).fetchall()
        conn.close()
        return {
            "active_count": int(total_row[0]) if total_row else 0,
            "by_type": {r["memory_type"] or "general": int(r["cnt"] or 0) for r in type_rows},
            "recent": [
                {
                    "id": int(r["id"]),
                    "memory_type": r["memory_type"],
                    "memory_text": (r["memory_text"] or "")[:140],
                    "importance_score": int(r["importance_score"] or 0),
                    "updated_at": r["updated_at"],
                }
                for r in recent_rows
            ],
        }
    except Exception:
        return {"active_count": 0, "by_type": {}, "recent": []}
