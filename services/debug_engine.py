from db import get_db, utc_now_iso


# --------------------------------------------------
# Health
# --------------------------------------------------

def build_health_payload(model_name: str) -> dict:
    """Trả về health status dict cho route /health."""
    return {
        "status":           "ok",
        "model":            model_name,
        "time":             utc_now_iso(),
        "pipeline_version": "V3.1+presence",
        "features": [
            "emotion", "intent", "consciousness",
            "biological", "internal_state", "momentum",
            "trust", "memory_threads", "life_graph",
            "relational_continuity", "emotional_echo",
            "gravity", "pronouns", "adaptive_tone",
            "personality_dna", "familiarity", "presence",
            "pattern_learning", "prompt_arbiter",
        ],
    }


# --------------------------------------------------
# Debug
# --------------------------------------------------

def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def build_debug_payload(limit: int = 20) -> dict:
    """
    Snapshot tất cả bảng chính, mỗi bảng tối đa `limit` rows.
    Dùng để kiểm tra DB state nhanh khi debug.
    """
    conn = get_db()

    def q(sql, *params):
        return _rows_to_list(conn.execute(sql, *params).fetchall())

    payload = {
        "users": q(
            "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
        ),
        "sessions": q(
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ),
        "messages": q(
            "SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ),
        "memory_nodes": q(
            "SELECT * FROM memory_nodes ORDER BY id DESC LIMIT ?", (limit,)
        ),
        "memory_summaries": q(
            "SELECT * FROM memory_summaries ORDER BY id DESC LIMIT ?", (limit,)
        ),
        "rate_limits": q(
            "SELECT * FROM rate_limits ORDER BY id DESC LIMIT ?", (limit,)
        ),
        "memory_decay_logs": q(
            "SELECT * FROM memory_decay_logs ORDER BY id DESC LIMIT ?", (limit,)
        ),
    }

    conn.close()
    return payload
