# --------------------------------------------------
# Relational Continuity Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Lớp hợp nhất các tín hiệu quan hệ dài hạn thành một
# snapshot nhất quán để prompt builder sử dụng.
#
# Hỏi và trả lời 6 câu hỏi ngầm:
#   1. Đây là giai đoạn nào của quan hệ?       → bond_stage
#   2. User đang sống trong arc nào?            → current_arc
#   3. Điều gì còn dang dở?                    → open_loops
#   4. Cảm xúc đang vận động theo hướng nào?   → last_emotional_direction
#   5. Nên reconnect thế nào?                   → reentry_style
#   6. Hải Đăng nên giữ posture nào lượt này?  → companion_posture
#
# Không gọi LLM. Không tạo bảng mới. Deterministic.
# Fail-safe: mọi exception → default context an toàn.
# --------------------------------------------------

from __future__ import annotations
import re
from datetime import datetime, timezone

from db import get_db

# --------------------------------------------------
# Constants
# --------------------------------------------------

# bond_stage thresholds
_BOND_TRUST_WARMING  = 0.35
_BOND_TRUST_TRUSTED  = 0.55
_BOND_TRUST_DEEP     = 0.70

_BOND_MSG_WARMING    = 5
_BOND_MSG_TRUSTED    = 20
_BOND_MSG_DEEP       = 60

_BOND_DAYS_TRUSTED   = 3
_BOND_DAYS_DEEP      = 14

# open_loop detection patterns (VI + EN)
_OPEN_LOOP_PATTERNS = [
    r"không biết (có nên|nên|có)",
    r"phân vân",
    r"(nên không|có nên|liệu có|liệu mình)",
    r"should i\b",
    r"don'?t know (if|whether|what)",
    r"(chưa biết|chưa quyết|chưa chốt)",
    r"(có thể|có lẽ) mình sẽ",
    r"(mình đang nghĩ|đang phân vân|đang cân nhắc)",
    r"(what should|how should|where should)",
    r"(còn đang|vẫn chưa|vẫn còn phân)",
]
_OPEN_LOOP_RE = re.compile("|".join(_OPEN_LOOP_PATTERNS), re.IGNORECASE)

# Arc keyword map — nhẹ hơn thread seeds, broad + fast
_ARC_KEYWORDS: dict[str, list[str]] = {
    "work_stress":      ["công việc", "deadline", "sếp", "áp lực", "job", "boss", "work stress",
                         "overtime", "kiệt sức", "burnout", "quá tải"],
    "creative_project": ["dự án", "xây dựng", "mebost", "hải đăng", "app", "startup",
                         "product", "design", "code", "prototype", "build", "launch"],
    "future_anxiety":   ["tương lai", "lo lắng", "sợ", "không biết sẽ ra sao", "uncertain",
                         "anxiety", "future", "worried about"],
    "loneliness":       ["cô đơn", "một mình", "không ai", "lonely", "alone", "isolated"],
    "self_doubt":       ["tự ti", "không đủ", "không giỏi", "thất bại", "worthless",
                         "not good enough", "failure", "imposter"],
    "relationship_pain":["người yêu", "chia tay", "bạn trai", "bạn gái", "heartbreak",
                         "breakup", "relationship", "hurt by"],
    "identity_shift":   ["mình là ai", "thay đổi", "khác đi", "identity", "who am i",
                         "changing", "lost myself"],
    "grief_loss":       ["mất", "buồn", "tang", "nhớ ai", "grief", "loss", "mourning",
                         "miss someone", "gone"],
    "health":           ["sức khoẻ", "bệnh", "đau", "mệt thể xác", "sick", "pain", "tired physically"],
    "personal_growth":  ["phát triển", "học", "thay đổi bản thân", "mục tiêu", "growth",
                         "learning", "self improve", "goal"],
}

# companion_posture labels
POSTURE_QUIET          = "quiet"
POSTURE_WARM           = "warm"
POSTURE_REFLECTIVE     = "reflective"
POSTURE_GROUNDING      = "grounding"
POSTURE_DEEP_REFLECTIVE= "deep_reflective"
POSTURE_BUILDER        = "builder_companion"


# --------------------------------------------------
# Public API
# --------------------------------------------------

def compute_relational_continuity(
    user_id: str,
    message: str,
    temporal_ctx: dict | None = None,
    trust: float = 0.30,
    momentum: float = 0.0,
    emotion_ctx: dict | None = None,
    internal_state: dict | None = None,
    memory_summary: str = "",
    life_graph_summary: dict | None = None,
) -> dict:
    """
    Tính toán relational snapshot lượt này.
    Trả về dict với 8 fields — không bao giờ raise.
    """
    try:
        return _compute(
            user_id, message, temporal_ctx or {},
            trust, momentum,
            emotion_ctx or {}, internal_state or {},
            memory_summary, life_graph_summary or {},
        )
    except Exception:
        return _default_ctx()


def continuity_prompt_hint(rel_ctx: dict) -> str:
    """
    Chuyển relational snapshot → 1 đoạn text ngắn inject vào system prompt.
    Ngắn, không lặp với trust/temporal/thread blocks đã có.
    """
    if not rel_ctx or rel_ctx.get("bond_stage") == "new":
        return ""

    lines: list[str] = []

    bond    = rel_ctx.get("bond_stage", "new")
    arc     = rel_ctx.get("current_arc")
    loops   = rel_ctx.get("open_loops", [])
    reentry = rel_ctx.get("reentry_style", "direct_continue")
    posture = rel_ctx.get("companion_posture", POSTURE_WARM)
    hint    = rel_ctx.get("continuity_hint", "")

    if hint:
        lines.append(hint)

    # Posture instruction
    posture_map = {
        POSTURE_QUIET:           "Lượt này giữ thật yên lặng và chứa đựng — không dẫn dắt.",
        POSTURE_WARM:            "Tiếp tục với sự ấm áp quen thuộc — user đã tin tưởng.",
        POSTURE_REFLECTIVE:      "Phản chiếu chậm — đây là lúc phù hợp để đi vào chiều sâu.",
        POSTURE_GROUNDING:       "Ổn định trước — mang lại cảm giác an toàn trước khi đi sâu.",
        POSTURE_DEEP_REFLECTIVE: "Không gian quan hệ đủ sâu — phản chiếu thật sự, không cần rào đón.",
        POSTURE_BUILDER:         "User đang xây dựng điều gì lớn — đồng hành như người cùng tạo dựng, không chỉ therapeutic.",
    }
    p_line = posture_map.get(posture, "")
    if p_line:
        lines.append(p_line)

    # Open loops — nhắc nhẹ, không áp
    if loops and bond in ("trusted", "deep"):
        loop_str = " / ".join(loops[:2])
        lines.append(f"Có thể nhắc nhẹ nếu tự nhiên: {loop_str}.")

    return "\n".join(lines) if lines else ""


def get_open_loops(user_id: str, limit: int = 3) -> list[str]:
    """
    Trả về tối đa `limit` open loops từ memory nodes + recent messages.
    Không bịa — chỉ từ dữ liệu có thật.
    """
    try:
        return _extract_open_loops(user_id, limit)
    except Exception:
        return []


def infer_bond_stage(
    trust: float,
    momentum: float,
    total_messages: int,
    relationship_days: int,
    active_thread_count: int,
    memory_node_count: int,
    session_continuity: str,
) -> str:
    """
    Deterministic: trả về "new" | "warming" | "trusted" | "deep".
    """
    # new: chưa có gì
    if session_continuity == "first_time" or total_messages < _BOND_MSG_WARMING:
        return "new"
    if trust < _BOND_TRUST_WARMING:
        return "new"

    # deep: cần tất cả 4 điều kiện
    if (trust >= _BOND_TRUST_DEEP
            and momentum >= 0.50
            and relationship_days >= _BOND_DAYS_DEEP
            and (active_thread_count >= 2 or memory_node_count >= 15)):
        return "deep"

    # trusted
    if (trust >= _BOND_TRUST_TRUSTED
            and total_messages >= _BOND_MSG_TRUSTED
            and relationship_days >= _BOND_DAYS_TRUSTED):
        return "trusted"

    # warming
    return "warming"


def infer_current_arc(
    active_threads: list[dict],
    memory_summary: str,
    message: str,
    life_graph_summary: dict,
) -> str | None:
    """
    Chọn arc nổi bật nhất — hybrid: thread history + current message signal.

    Ưu tiên thực tế:
      1. Keyword signal mạnh từ message hiện tại (user đang nói về gì NGAY BÂY GIỜ)
         vượt qua thread history nếu score đủ mạnh (>= 3 keywords)
      2. Active thread với thread_score cao (history dài hạn)
      3. Keyword heuristic từ memory_summary
      4. Life graph nodes
      5. None
    """
    _thread_to_arc = {
        "work_stress":    "work_stress",
        "loneliness":     "loneliness",
        "relationship":   "relationship_pain",
        "anxiety_fear":   "future_anxiety",
        "self_doubt":     "self_doubt",
        "health":         "health",
        "personal_growth":"personal_growth",
        "grief_loss":     "grief_loss",
    }

    # --- Step 1: Keyword signal từ message + memory_summary (current context) ---
    combined_current = (message + " " + memory_summary).lower()
    arc_scores: dict[str, int] = {}
    for arc_id, keywords in _ARC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in combined_current)
        if score > 0:
            arc_scores[arc_id] = score

    # Arc mạnh nhất từ current context
    best_current_arc   = max(arc_scores, key=arc_scores.get) if arc_scores else None
    best_current_score = arc_scores.get(best_current_arc, 0) if best_current_arc else 0

    # Nếu message hiện tại nói rõ về 1 arc (>= 3 keywords) → ưu tiên nó
    if best_current_arc and best_current_score >= 3:
        return best_current_arc

    # --- Step 2: Active threads (history) ---
    if active_threads:
        # Combine thread score với signal từ current message
        best_thread_arc   = None
        best_combined     = 0.0
        for t in active_threads:
            tid         = t.get("thread_id", "")
            arc         = _thread_to_arc.get(tid, tid)
            t_score     = float(t.get("score", 0))
            msg_signal  = arc_scores.get(arc, 0) / 10.0   # normalise
            combined_sc = t_score + msg_signal
            if combined_sc > best_combined:
                best_combined     = combined_sc
                best_thread_arc   = arc
        if best_thread_arc and best_combined >= 0.18:
            # Nhưng nếu current arc signal > 0 và khác thread arc → ưu tiên current
            if best_current_arc and best_current_arc != best_thread_arc and best_current_score >= 2:
                return best_current_arc
            return best_thread_arc

    # --- Step 3: Fallback keyword từ memory summary ---
    if best_current_arc and best_current_score >= 2:
        return best_current_arc

    # --- Step 4: Life graph nodes ---
    if life_graph_summary:
        nodes_text = " ".join(
            str(n.get("label","")) for n in life_graph_summary.get("nodes", [])
        ).lower()
        for arc_id, keywords in _ARC_KEYWORDS.items():
            if any(kw in nodes_text for kw in keywords[:3]):
                return arc_id

    return None


def infer_reentry_style(
    session_continuity: str,
    bond_stage: str,
    time_gap_minutes: float,
    last_emotional_direction: str,
) -> str:
    """
    "first_contact" | "direct_continue" | "gentle_resume"
    | "warm_return" | "soft_reopen"
    """
    if session_continuity == "first_time" or bond_stage == "new":
        return "first_contact"

    if session_continuity == "continuous":
        return "direct_continue"

    # pause = < 6 giờ
    if session_continuity == "pause":
        return "gentle_resume"

    # return = > 6 giờ
    # warm_return: bond đủ + không nặng cảm xúc
    if bond_stage in ("trusted", "deep") and last_emotional_direction not in ("heavy", "rising"):
        return "warm_return"

    # soft_reopen: có arc nặng chưa giải quyết
    if last_emotional_direction in ("heavy", "rising") or bond_stage == "warming":
        return "soft_reopen"

    return "warm_return"


def infer_companion_posture(
    bond_stage: str,
    current_arc: str | None,
    trust: float,
    momentum: float,
    distress: float,
    last_emotional_direction: str,
    reentry_style: str,
) -> str:
    """
    Chọn companion posture.
    Safety > Connection > Arc-awareness > Depth.
    """
    # Safety first
    if distress >= 0.70 or trust < 0.30:
        return POSTURE_GROUNDING

    # First contact
    if reentry_style == "first_contact":
        return POSTURE_QUIET

    # Soft reopen — cần ổn định trước
    if reentry_style == "soft_reopen":
        return POSTURE_GROUNDING if distress >= 0.40 else POSTURE_WARM

    # Creative / builder arc — bao gồm cả work_stress nếu có creative signal rõ
    # builder_companion không chỉ khi arc == creative_project
    # mà khi: (1) arc là creative, HOẶC
    #          (2) arc là work_stress nhưng distress thấp + bond deep + message có build/project keywords
    _CREATIVE_ARCS = {"creative_project", "personal_growth"}
    _builder_signal = current_arc in _CREATIVE_ARCS
    if current_arc == "work_stress" and distress < 0.40 and bond_stage == "deep":
        # work_stress có thể là "đang xây dựng và bận" chứ không phải burnout
        _builder_signal = True   # conservative fallback — posture tốt hơn deep_reflective cho builder
    if _builder_signal:
        if bond_stage in ("trusted", "deep") and momentum >= 0.30:
            return POSTURE_BUILDER

    # Deep arc + high trust + bond
    if bond_stage == "deep" and trust >= 0.70 and last_emotional_direction in ("settling", "hopeful", "unclear"):
        return POSTURE_DEEP_REFLECTIVE

    # Arc nặng + warming
    if current_arc in ("grief_loss", "self_doubt", "relationship_pain") and trust >= 0.45:
        return POSTURE_REFLECTIVE

    # Default theo bond
    if bond_stage in ("trusted", "deep"):
        return POSTURE_REFLECTIVE if momentum >= 0.50 else POSTURE_WARM

    return POSTURE_WARM


# --------------------------------------------------
# Internal — main compute
# --------------------------------------------------

def _compute(
    user_id: str,
    message: str,
    temporal_ctx: dict,
    trust: float,
    momentum: float,
    emotion_ctx: dict,
    internal_state: dict,
    memory_summary: str,
    life_graph_summary: dict,
) -> dict:
    session_continuity = temporal_ctx.get("session_continuity", "first_time")
    relationship_days  = temporal_ctx.get("relationship_days", 0)
    time_gap_minutes   = temporal_ctx.get("time_gap_minutes", 0.0)
    distress           = internal_state.get("distress", 0.0) or emotion_ctx.get("distress", 0.0)

    # ── DB queries ───────────────────────────────
    total_messages, memory_node_count = _get_message_and_memory_counts(user_id)

    # ── Active threads ────────────────────────────
    try:
        from services.memory_threading_engine import get_active_threads
        active_threads = get_active_threads(user_id, top_n=3)
    except Exception:
        active_threads = []

    # ── Emotion direction ─────────────────────────
    last_emotional_direction = _infer_emotional_direction(user_id, emotion_ctx)

    # ── bond_stage ───────────────────────────────
    bond_stage = infer_bond_stage(
        trust               = trust,
        momentum            = momentum,
        total_messages      = total_messages,
        relationship_days   = relationship_days,
        active_thread_count = len(active_threads),
        memory_node_count   = memory_node_count,
        session_continuity  = session_continuity,
    )

    # ── current_arc ──────────────────────────────
    current_arc = infer_current_arc(
        active_threads      = active_threads,
        memory_summary      = memory_summary,
        message             = message,
        life_graph_summary  = life_graph_summary,
    )

    # ── open_loops ───────────────────────────────
    open_loops = _extract_open_loops(user_id, limit=3)

    # ── reentry_style ─────────────────────────────
    reentry_style = infer_reentry_style(
        session_continuity        = session_continuity,
        bond_stage                = bond_stage,
        time_gap_minutes          = time_gap_minutes,
        last_emotional_direction  = last_emotional_direction,
    )

    # ── companion_posture ─────────────────────────
    companion_posture = infer_companion_posture(
        bond_stage               = bond_stage,
        current_arc              = current_arc,
        trust                    = trust,
        momentum                 = momentum,
        distress                 = distress,
        last_emotional_direction = last_emotional_direction,
        reentry_style            = reentry_style,
    )

    # ── continuity_score ─────────────────────────
    continuity_score = _compute_continuity_score(
        trust, momentum, relationship_days, memory_node_count,
        len(active_threads), bond_stage,
    )

    # ── continuity_hint ──────────────────────────
    continuity_hint = _build_continuity_hint(
        bond_stage, reentry_style, current_arc, last_emotional_direction,
    )

    return {
        "bond_stage":               bond_stage,
        "current_arc":              current_arc,
        "open_loops":               open_loops,
        "last_emotional_direction": last_emotional_direction,
        "reentry_style":            reentry_style,
        "companion_posture":        companion_posture,
        "continuity_score":         round(continuity_score, 3),
        "continuity_hint":          continuity_hint,
    }


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _get_message_and_memory_counts(user_id: str) -> tuple[int, int]:
    try:
        db = get_db()
        msg_row = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        mem_row = db.execute(
            "SELECT COUNT(*) FROM memory_nodes WHERE user_id = ? AND deleted_flag = 0",
            (user_id,),
        ).fetchone()
        db.close()
        return int(msg_row[0] if msg_row else 0), int(mem_row[0] if mem_row else 0)
    except Exception:
        return 0, 0


def _infer_emotional_direction(user_id: str, current_emotion_ctx: dict) -> str:
    """
    Dựa trên 5 emotion logs gần nhất.

    heavy     — emotion nặng gần đây, không giảm
    settling  — intensity giảm dần, có dấu hiệu an toàn
    rising    — intensity tăng dần hoặc anxious tăng
    hopeful   — happy/calm/relief xuất hiện sau giai đoạn nặng
    unclear   — không đủ dữ liệu
    """
    try:
        db   = get_db()
        rows = db.execute(
            """SELECT emotion, timestamp FROM emotion_logs
               WHERE user_id = ? ORDER BY id DESC LIMIT 8""",
            (user_id,),
        ).fetchall()
        db.close()
    except Exception:
        return "unclear"

    if not rows or len(rows) < 2:
        return "unclear"

    # Map emotion → weight (nặng cao hơn)
    _HEAVY   = {"anxious", "sad", "angry", "scared", "overwhelmed", "grief",
                "frustrated", "desperate", "hopeless"}
    _CALM    = {"happy", "calm", "hopeful", "relieved", "grateful", "peaceful"}
    _NEUTRAL = {"neutral", "tired", "confused"}

    def _score(emotion: str) -> float:
        e = emotion.lower()
        if e in _HEAVY:   return 0.0    # thấp = nặng
        if e in _CALM:    return 1.0    # cao = nhẹ
        return 0.5

    scores = [_score(r[0] if isinstance(r, (list, tuple)) else r["emotion"]) for r in rows]
    # rows[0] = most recent
    recent5  = scores[:5]
    older    = scores[5:] if len(scores) > 5 else scores[1:]

    avg_recent = sum(recent5) / len(recent5)
    avg_older  = sum(older) / len(older) if older else avg_recent

    # Kết hợp với current emotion
    cur_emotion    = current_emotion_ctx.get("emotion", "neutral").lower()
    cur_intensity  = current_emotion_ctx.get("intensity", 5)

    # hopeful: hiện tại calm/happy sau giai đoạn nặng
    if cur_emotion in _CALM and avg_older < 0.45:
        return "hopeful"

    # settling: trend giảm nặng
    if avg_recent > avg_older + 0.10:
        return "settling"

    # rising: trend tăng nặng
    if avg_older > avg_recent + 0.10 and avg_recent < 0.40:
        return "rising"

    # heavy: trung bình nặng, không giảm
    if avg_recent < 0.35:
        return "heavy"

    # unclear
    return "unclear"


def _extract_open_loops(user_id: str, limit: int = 3) -> list[str]:
    """
    Tìm open loops từ:
    1. memory_nodes có keyword phân vân / should I
    2. recent user messages (7 messages gần nhất)
    """
    candidates: list[tuple[float, str]] = []  # (importance, text_snippet)

    try:
        db = get_db()

        # Từ memory nodes
        mem_rows = db.execute(
            """SELECT memory_text, importance_score, created_at
               FROM memory_nodes
               WHERE user_id = ? AND deleted_flag = 0
               ORDER BY importance_score DESC, created_at DESC LIMIT 30""",
            (user_id,),
        ).fetchall()

        for r in mem_rows:
            txt = r[0] if isinstance(r, (list, tuple)) else r["memory_text"]
            imp = float(r[1] if isinstance(r, (list, tuple)) else r["importance_score"])
            if txt and _OPEN_LOOP_RE.search(txt):
                snippet = _truncate(txt, 60)
                candidates.append((imp, snippet))

        # Từ recent messages
        msg_rows = db.execute(
            """SELECT message_text, importance_score FROM messages
               WHERE user_id = ? AND role = 'user'
               ORDER BY id DESC LIMIT 7""",
            (user_id,),
        ).fetchall()

        for r in msg_rows:
            txt = r[0] if isinstance(r, (list, tuple)) else r["message_text"]
            imp = float(r[1] if isinstance(r, (list, tuple)) else (r["importance_score"] or 3))
            if txt and _OPEN_LOOP_RE.search(txt):
                snippet = _truncate(txt, 60)
                if not any(snippet in c[1] for c in candidates):  # dedup
                    candidates.append((imp, snippet))

        db.close()

    except Exception:
        return []

    # Sort by importance desc, dedup, limit
    candidates.sort(key=lambda x: x[0], reverse=True)
    seen, result = set(), []
    for _, snippet in candidates:
        key = snippet[:30]
        if key not in seen:
            seen.add(key)
            result.append(snippet)
        if len(result) >= limit:
            break

    return result


def _compute_continuity_score(
    trust: float,
    momentum: float,
    relationship_days: int,
    memory_node_count: int,
    active_thread_count: int,
    bond_stage: str,
) -> float:
    """
    0.0 = hoàn toàn mới / rời rạc
    1.0 = quan hệ sâu có continuity cao
    """
    _BOND_BASE = {"new": 0.0, "warming": 0.25, "trusted": 0.55, "deep": 0.80}
    base = _BOND_BASE.get(bond_stage, 0.0)

    # Bonus từ memory + threads
    mem_bonus    = min(memory_node_count / 30.0, 0.10)
    thread_bonus = min(active_thread_count / 5.0, 0.05)
    trust_bonus  = (trust - 0.30) * 0.10 if trust > 0.30 else 0.0
    day_bonus    = min(relationship_days / 30.0, 0.05)

    return min(1.0, base + mem_bonus + thread_bonus + trust_bonus + day_bonus)


def _build_continuity_hint(
    bond_stage: str,
    reentry_style: str,
    current_arc: str | None,
    last_emotional_direction: str,
) -> str:
    """
    1 câu ngắn để inject vào prompt — tóm tắt trạng thái continuity.
    """
    _REENTRY_HINTS = {
        "first_contact":   "Lần đầu gặp — tạo không gian, không đặt kỳ vọng.",
        "direct_continue": "Cuộc trò chuyện đang tiếp diễn — tiếp tục mạch tự nhiên.",
        "gentle_resume":   "User quay lại sau một lúc — kết nối nhẹ, không nhảy thẳng vào nội dung.",
        "warm_return":     "User trở về — đón nhận ấm áp, không nhắc lại quá nhiều.",
        "soft_reopen":     "User trở về sau khoảng thời gian với chủ đề còn dang dở — nhẹ nhàng, không ép mở.",
    }

    base = _REENTRY_HINTS.get(reentry_style, "")

    # Bổ sung arc context nếu có
    _ARC_HINTS = {
        "creative_project":  "User đang trong hành trình xây dựng.",
        "work_stress":       "Áp lực công việc là chủ đề hiện tại.",
        "future_anxiety":    "Lo lắng về tương lai đang hiện diện.",
        "loneliness":        "Cô đơn là sợi chỉ đang chạy trong câu chuyện.",
        "self_doubt":        "Sự tự ti đang ảnh hưởng đến cách user nhìn bản thân.",
        "relationship_pain": "Đau từ mối quan hệ vẫn còn đó.",
        "grief_loss":        "Mất mát vẫn đang được mang.",
        "identity_shift":    "User đang đi qua giai đoạn thay đổi về bản sắc.",
    }
    arc_hint = _ARC_HINTS.get(current_arc or "", "")

    parts = [p for p in [base, arc_hint] if p]
    return " ".join(parts)


def _truncate(text: str, max_chars: int) -> str:
    text = text.strip().replace("\n", " ")
    return text[:max_chars].rstrip() + ("…" if len(text) > max_chars else "")


# --------------------------------------------------
# Prompt block for prompt_builder.py
# --------------------------------------------------

def relational_prompt_block(rel_ctx: dict) -> str:
    """
    Tạo block text để inject vào system prompt.
    Ngắn, cụ thể, không lặp với trust/temporal đã có.
    """
    if not rel_ctx:
        return ""

    bond     = rel_ctx.get("bond_stage", "new")
    arc      = rel_ctx.get("current_arc")
    loops    = rel_ctx.get("open_loops", [])
    posture  = rel_ctx.get("companion_posture", POSTURE_WARM)
    reentry  = rel_ctx.get("reentry_style", "direct_continue")
    score    = rel_ctx.get("continuity_score", 0.0)
    hint     = rel_ctx.get("continuity_hint", "")
    direction= rel_ctx.get("last_emotional_direction", "unclear")

    if bond == "new" and reentry == "first_contact":
        return ""  # không inject gì cho người mới — tránh cảm giác phân tích

    lines = ["── Relational context ──"]

    # Bond + posture
    _BOND_LABELS = {
        "warming": "Mới bắt đầu tin tưởng",
        "trusted": "Quan hệ đã có độ tin cậy",
        "deep":    "Quan hệ sâu, continuity thực sự",
    }
    b_label = _BOND_LABELS.get(bond, "")
    if b_label:
        lines.append(f"Giai đoạn: {b_label}.")

    # Posture
    _POSTURE_LABELS = {
        POSTURE_QUIET:           "Giữ yên lặng, chứa đựng.",
        POSTURE_WARM:            "Ấm áp, quen thuộc.",
        POSTURE_REFLECTIVE:      "Phản chiếu chậm.",
        POSTURE_GROUNDING:       "Ổn định, grounding trước.",
        POSTURE_DEEP_REFLECTIVE: "Chiều sâu thật sự.",
        POSTURE_BUILDER:         "Đồng hành xây dựng — companion trong hành trình dài.",
    }
    p_label = _POSTURE_LABELS.get(posture, "")
    if p_label:
        lines.append(f"Posture lượt này: {p_label}")

    # Arc
    _ARC_LABELS = {
        "work_stress":      "áp lực công việc",
        "creative_project": "xây dựng dự án sáng tạo",
        "future_anxiety":   "lo lắng về tương lai",
        "loneliness":       "cô đơn / thiếu kết nối",
        "self_doubt":       "tự ti / nghi ngờ bản thân",
        "relationship_pain":"đau từ mối quan hệ",
        "identity_shift":   "thay đổi bản sắc",
        "grief_loss":       "mất mát / buồn đau",
        "health":           "sức khoẻ",
        "personal_growth":  "phát triển cá nhân",
    }
    if arc:
        a_label = _ARC_LABELS.get(arc, arc)
        lines.append(f"Arc hiện tại: {a_label}.")

    # Emotional direction
    if direction not in ("unclear",):
        _DIR = {
            "heavy":    "Cảm xúc đang nặng — không khai thác thêm.",
            "settling": "Cảm xúc đang lắng dần — có thể đồng hành nhẹ.",
            "rising":   "Cảm xúc đang leo thang — ổn định trước.",
            "hopeful":  "Có dấu hiệu nhẹ hơn — giữ không gian đó.",
        }
        d_hint = _DIR.get(direction, "")
        if d_hint:
            lines.append(d_hint)

    # Open loops — chỉ khi bond đủ
    if loops and bond in ("trusted", "deep"):
        lines.append(
            "Open loops có thể nhắc nhẹ nếu tự nhiên: "
            + "; ".join(loops[:2]) + "."
        )

    # Continuity hint
    if hint:
        lines.append(hint)

    return "\n".join(lines)


# --------------------------------------------------
# Default safe context
# --------------------------------------------------

def _default_ctx() -> dict:
    return {
        "bond_stage":               "new",
        "current_arc":              None,
        "open_loops":               [],
        "last_emotional_direction": "unclear",
        "reentry_style":            "first_contact",
        "companion_posture":        POSTURE_WARM,
        "continuity_score":         0.0,
        "continuity_hint":          "",
    }
