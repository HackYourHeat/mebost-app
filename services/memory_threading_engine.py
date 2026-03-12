# --------------------------------------------------
# Memory Threading Engine — MEBOST Hải Đăng V2.2
# --------------------------------------------------
# Gom memory_nodes thành life threads — dòng câu chuyện dài hạn.
# Không thay đổi memory_engine.
# Không gọi LLM — dùng keyword overlap thuần.
#
# Tables dùng:
#   memory_nodes        (đọc, không sửa)
#   life_threads        (đã có — upsert)
#   memory_thread_links (mới — nối node ↔ thread)
#
# Flow khi có memory node mới:
#   assign_node_to_thread(user_id, node_id, memory_text, importance)
#     → extract keywords
#     → find best matching thread
#     → attach hoặc create new thread
#     → update thread score
# --------------------------------------------------

from __future__ import annotations
import re
from datetime import datetime, timezone

from db import get_db, utc_now_iso

# --------------------------------------------------
# Thread keyword definitions
# Mỗi thread có seed keywords — overlap với node text → attach
# --------------------------------------------------

_THREAD_SEEDS: dict[str, list[str]] = {
    "work_stress":       ["công việc", "sếp", "deadline", "áp lực", "overtime", "burnout",
                          "work", "job", "boss", "pressure", "workload", "tired of work",
                          "làm thêm", "overtime", "quá tải", "kiệt sức"],
    "loneliness":        ["cô đơn", "một mình", "không ai hiểu", "cô lập", "thiếu bạn",
                          "lonely", "alone", "isolated", "no friends", "no one understands"],
    "relationship":      ["người yêu", "bạn trai", "bạn gái", "gia đình", "bố mẹ", "anh chị",
                          "relationship", "partner", "boyfriend", "girlfriend", "family", "parents"],
    "anxiety_fear":      ["lo lắng", "sợ", "lo âu", "hồi hộp", "bất an",
                          "anxious", "scared", "fear", "panic", "worry"],
    "self_doubt":        ["tự ti", "không đủ giỏi", "thất bại", "không xứng",
                          "self doubt", "not good enough", "failure", "worthless"],
    "health":            ["sức khoẻ", "bệnh", "mệt mỏi thể xác", "đau",
                          "health", "sick", "pain", "exhausted physically"],
    "personal_growth":   ["phát triển", "học hỏi", "thay đổi bản thân", "mục tiêu",
                          "growth", "learning", "change", "goal", "improve"],
    "grief_loss":        ["mất mát", "đau buồn", "tang", "nhớ",
                          "grief", "loss", "mourning", "miss someone"],
}

_OVERLAP_THRESHOLD = 1      # ít nhất 1 keyword trùng → attach
_DECAY_RATE        = 0.10   # activity decay per 7 days of inactivity


# --------------------------------------------------
# Migration
# --------------------------------------------------

def ensure_thread_link_table() -> None:
    """Tạo memory_thread_links nếu chưa có."""
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory_thread_links (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    TEXT,
                thread_id  TEXT,
                node_id    INTEGER,
                created_at TEXT
            )
        """)
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Keyword extraction
# --------------------------------------------------

def _extract_keywords(text: str) -> set[str]:
    """Tokenise + lowercase — trả về set từ ngắn."""
    words = set(re.findall(r"[a-zA-Zàáâãèéêìíòóôõùúăđĩũơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]+", text.lower()))
    return words


def _overlap_score(text_original_lower: str, seed_keywords: list[str]) -> int:
    """Đếm số seed keywords xuất hiện trong text gốc (lowercase)."""
    count = 0
    for kw in seed_keywords:
        if kw in text_original_lower:
            count += 1
    return count


# --------------------------------------------------
# Thread matching
# --------------------------------------------------

def _find_best_thread(memory_text: str) -> str | None:
    """
    So sánh text với tất cả _THREAD_SEEDS.
    Trả về thread_id có overlap cao nhất, hoặc None.
    """
    low     = memory_text.lower()
    best_id = None
    best_sc = 0

    for thread_id, seeds in _THREAD_SEEDS.items():
        sc = _overlap_score(low, seeds)
        if sc > best_sc:
            best_sc = sc
            best_id = thread_id

    return best_id if best_sc >= _OVERLAP_THRESHOLD else None


# --------------------------------------------------
# Thread score
# --------------------------------------------------

def _compute_thread_score(
    avg_importance: float,
    recent_activity: float,
    frequency: int,
) -> float:
    freq_norm = min(frequency / 10.0, 1.0)
    return round(
        0.5 * avg_importance / 10.0
        + 0.3 * recent_activity
        + 0.2 * freq_norm,
        3,
    )


def _recency_score(last_activity_iso: str | None) -> float:
    """1.0 = today, decays over time."""
    if not last_activity_iso:
        return 0.5
    try:
        dt    = datetime.fromisoformat(last_activity_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days  = (datetime.now(timezone.utc) - dt).days
        weeks = days / 7.0
        return round(max(0.0, 1.0 - _DECAY_RATE * weeks), 3)
    except Exception:
        return 0.5


# --------------------------------------------------
# Main API
# --------------------------------------------------

def assign_node_to_thread(
    user_id: str,
    node_id: int,
    memory_text: str,
    importance: int,
) -> str | None:
    """
    Gán memory node vào thread phù hợp.
    Trả về thread_id đã gán, hoặc None nếu không match.
    """
    thread_id = _find_best_thread(memory_text)
    if not thread_id:
        return None

    try:
        db   = get_db()
        now  = utc_now_iso()

        # Upsert life_threads
        row = db.execute(
            "SELECT node_count, emotional_weight, last_activity FROM life_threads "
            "WHERE thread_id = ? AND user_id = ?",
            (thread_id, user_id),
        ).fetchone()

        if row:
            old_weight  = float(row["emotional_weight"] or 0.5)
            old_count   = int(row["node_count"] or 1)
            # Running average of emotional weight (proxy = importance/10)
            new_weight  = round((old_weight * old_count + importance / 10.0) / (old_count + 1), 3)
            db.execute(
                """UPDATE life_threads
                   SET node_count = node_count + 1,
                       emotional_weight = ?,
                       last_activity = ?
                   WHERE thread_id = ? AND user_id = ?""",
                (new_weight, now, thread_id, user_id),
            )
        else:
            db.execute(
                """INSERT INTO life_threads
                   (thread_id, user_id, name, emotional_weight, last_activity, node_count)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (thread_id, user_id, _thread_label(thread_id),
                 round(importance / 10.0, 3), now),
            )

        # Link node → thread
        db.execute(
            "INSERT INTO memory_thread_links (user_id, thread_id, node_id, created_at) VALUES (?,?,?,?)",
            (user_id, thread_id, node_id, now),
        )
        db.commit()
        db.close()

    except Exception:
        pass

    return thread_id


def get_active_threads(user_id: str, top_n: int = 3) -> list[dict]:
    """
    Trả về top_n threads hoạt động gần nhất, với score.
    Dùng để inject vào prompt.
    """
    try:
        db   = get_db()
        rows = db.execute(
            """SELECT thread_id, name, emotional_weight, last_activity, node_count
               FROM life_threads WHERE user_id = ?
               ORDER BY last_activity DESC LIMIT 20""",
            (user_id,),
        ).fetchall()
        db.close()

        scored = []
        for r in rows:
            rec    = _recency_score(r["last_activity"])
            score  = _compute_thread_score(
                float(r["emotional_weight"] or 0.5) * 10,
                rec,
                int(r["node_count"] or 1),
            )
            scored.append({
                "thread_id":   r["thread_id"],
                "name":        r["name"] or _thread_label(r["thread_id"]),
                "score":       score,
                "recency":     rec,
                "node_count":  r["node_count"],
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_n]

    except Exception:
        return []


def threads_prompt_block(threads: list[dict]) -> str:
    """Tạo đoạn text ngắn để inject vào system prompt."""
    if not threads:
        return ""
    lines = ["Chủ đề cuộc sống đang hoạt động:"]
    labels = {"work_stress":"Áp lực công việc","loneliness":"Cô đơn / kết nối",
               "relationship":"Mối quan hệ","anxiety_fear":"Lo âu / sợ hãi",
               "self_doubt":"Tự ti / nghi ngờ bản thân","health":"Sức khoẻ",
               "personal_growth":"Phát triển cá nhân","grief_loss":"Mất mát / buồn đau"}
    for t in threads:
        name   = labels.get(t["thread_id"], t["name"])
        recstr = "gần đây" if t["recency"] >= 0.7 else ("đang diễn ra" if t["recency"] >= 0.4 else "cũ hơn")
        lines.append(f"• {name} ({recstr}, {t['node_count']} ký ức)")
    lines.append("Nếu phù hợp, có thể nhắc lại tự nhiên — không gượng ép.")
    return "\n".join(lines)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _thread_label(thread_id: str) -> str:
    return thread_id.replace("_", " ").title()
