from datetime import timezone, datetime

from db import get_db, utc_now_iso
from services.memory_summary_engine import save_memory_summary

# --------------------------------------------------
# Config
# --------------------------------------------------

MEMORY_DECAY_DAYS     = 14
MEMORY_DECAY_STEP     = 1
MIN_MEMORY_IMPORTANCE = 3

_DECAY_THRESHOLD_SECS = MEMORY_DECAY_DAYS * 24 * 60 * 60


# --------------------------------------------------
# Time helpers
# --------------------------------------------------

def parse_iso_to_ts(iso_str: str) -> int:
    """
    Parse ISO timestamp string → unix timestamp int.
    Trả về 0 nếu rỗng hoặc lỗi parse.
    """
    if not iso_str:
        return 0
    try:
        # Hỗ trợ cả "Z" suffix và offset-naive
        normalized = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (ValueError, TypeError):
        return 0


def now_ts() -> int:
    """Trả về unix timestamp hiện tại (UTC)."""
    return int(datetime.now(timezone.utc).timestamp())


def should_decay_memory(reference_ts: int, current_ts: int) -> bool:
    """True nếu reference_ts đã quá MEMORY_DECAY_DAYS so với current_ts."""
    return reference_ts < (current_ts - _DECAY_THRESHOLD_SECS)


# --------------------------------------------------
# Internal: log one decay event
# --------------------------------------------------

def _log_decay(
    cur,
    user_id: str,
    memory_node_id: int,
    old_score: int,
    new_score: int,
) -> None:
    """Insert một dòng vào memory_decay_logs (dùng cursor đang mở)."""
    cur.execute(
        """INSERT INTO memory_decay_logs
           (user_id, memory_node_id, old_importance_score, new_importance_score, decayed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, memory_node_id, old_score, new_score, utc_now_iso()),
    )


# --------------------------------------------------
# Public: log_decay  (standalone helper nếu cần gọi ngoài)
# --------------------------------------------------

def log_decay(
    user_id: str,
    memory_node_id: int,
    old_score: int,
    new_score: int,
) -> None:
    """Insert decay log, dùng connection riêng."""
    conn = get_db()
    _log_decay(conn.cursor(), user_id, memory_node_id, old_score, new_score)
    conn.commit()
    conn.close()


# --------------------------------------------------
# Public: decay_memory_nodes
# --------------------------------------------------

def decay_memory_nodes(user_id: str) -> bool:
    """
    Giảm importance_score của các memory node lâu không dùng.

    Returns:
        True  — nếu có ít nhất một node bị decay (summary sẽ được rebuild)
        False — nếu không có gì thay đổi
    """
    conn    = get_db()
    cur     = conn.cursor()
    current = now_ts()
    changed = False

    rows = cur.execute(
        """SELECT id, importance_score, last_used_at, updated_at
           FROM memory_nodes
           WHERE user_id     = ?
             AND deleted_flag = 0
           ORDER BY id DESC""",
        (user_id,),
    ).fetchall()

    for row in rows:
        old_score = row["importance_score"] or 0

        # Dùng last_used_at nếu có, fallback sang updated_at
        ref_str = row["last_used_at"] or row["updated_at"] or ""
        ref_ts  = parse_iso_to_ts(ref_str)

        if not should_decay_memory(ref_ts, current):
            continue
        if old_score <= MIN_MEMORY_IMPORTANCE:
            continue

        new_score = max(MIN_MEMORY_IMPORTANCE, old_score - MEMORY_DECAY_STEP)
        if new_score == old_score:
            continue

        cur.execute(
            """UPDATE memory_nodes
               SET importance_score = ?,
                   updated_at       = ?
               WHERE id = ?""",
            (new_score, utc_now_iso(), row["id"]),
        )
        _log_decay(cur, user_id, row["id"], old_score, new_score)
        changed = True

    conn.commit()
    conn.close()

    if changed:
        save_memory_summary(user_id)

    return changed
