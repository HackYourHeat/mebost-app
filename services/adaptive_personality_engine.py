# --------------------------------------------------
# Adaptive Personality Engine — MEBOST V1.4
# --------------------------------------------------
# Hải Đăng học cách thích nghi với từng người.
# Personality profile hình thành qua thời gian từ:
#   - cách user viết
#   - feedback
#   - conversation depth
#   - emotion history
# --------------------------------------------------

from __future__ import annotations
from db import get_db, utc_now_iso

# --------------------------------------------------
# Defaults
# --------------------------------------------------

PERSONALITY_DEFAULTS = {
    "empathy_level":      0.7,   # 0.0–1.0
    "question_frequency": 0.5,   # 0.0–1.0
    "reflection_depth":   0.5,   # 0.0–1.0
    "guidance_strength":  0.2,   # 0.0–1.0  (thấp = ít hướng dẫn)
    "warmth_level":       0.7,   # 0.0–1.0
}

# Tốc độ học — bước mỗi update
_LEARN_RATE = 0.06


# --------------------------------------------------
# DB
# --------------------------------------------------

def get_personality(user_id: str) -> dict[str, float]:
    """Lấy personality profile. Default nếu chưa có."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM personality_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()
        if row:
            return {
                "empathy_level":      float(row["empathy_level"]      or 0.7),
                "question_frequency": float(row["question_frequency"] or 0.5),
                "reflection_depth":   float(row["reflection_depth"]   or 0.5),
                "guidance_strength":  float(row["guidance_strength"]  or 0.2),
                "warmth_level":       float(row["warmth_level"]       or 0.7),
            }
    except Exception:
        pass
    return dict(PERSONALITY_DEFAULTS)


def _save_personality(user_id: str, p: dict[str, float]) -> None:
    try:
        db = get_db()
        db.execute(
            """INSERT INTO personality_profile
               (user_id, empathy_level, question_frequency, reflection_depth,
                guidance_strength, warmth_level, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 empathy_level      = excluded.empathy_level,
                 question_frequency = excluded.question_frequency,
                 reflection_depth   = excluded.reflection_depth,
                 guidance_strength  = excluded.guidance_strength,
                 warmth_level       = excluded.warmth_level,
                 updated_at         = excluded.updated_at""",
            (
                user_id,
                p["empathy_level"], p["question_frequency"],
                p["reflection_depth"], p["guidance_strength"], p["warmth_level"],
                utc_now_iso(),
            ),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Learning logic
# --------------------------------------------------

def _nudge(value: float, direction: float, rate: float = _LEARN_RATE) -> float:
    """Dịch chuyển value theo direction (+1 = tăng, -1 = giảm), clamp [0,1]."""
    return round(min(1.0, max(0.0, value + direction * rate)), 3)


def learn_from_signals(
    user_id: str,
    signals: dict[str, float],
    internal_state: dict[str, float],
    emotion_intensity: int,
    conversation_turn: int,
) -> dict[str, float]:
    """
    Cập nhật personality dựa trên signals + trạng thái hiện tại.

    Rules:
      distress cao      → empathy_level tăng, guidance_strength giảm
      help_seeking cao  → guidance_strength tăng nhẹ
      salience cao      → reflection_depth tăng
      trust cao         → warmth_level tăng nhẹ
      nhiều câu hỏi?    → question_frequency giảm (tránh quá)
      depth cao (state) → reflection_depth tăng
    """
    p = get_personality(user_id)

    if signals.get("distress", 0) >= 0.5:
        p["empathy_level"]     = _nudge(p["empathy_level"],     +1)
        p["guidance_strength"] = _nudge(p["guidance_strength"], -1)

    if signals.get("help_seeking", 0) >= 0.5:
        p["guidance_strength"] = _nudge(p["guidance_strength"], +1)

    if signals.get("salience", 0) >= 0.4:
        p["reflection_depth"]  = _nudge(p["reflection_depth"],  +1)

    if signals.get("safety", 0) >= 0.5:
        p["warmth_level"]      = _nudge(p["warmth_level"],      +1)

    if internal_state.get("depth", 0) >= 0.5:
        p["reflection_depth"]  = _nudge(p["reflection_depth"],  +1)

    if internal_state.get("trust", 0) >= 0.6:
        p["warmth_level"]      = _nudge(p["warmth_level"],      +0.5)

    # Conversation depth — sâu hơn theo thời gian nếu user tiếp tục
    if conversation_turn >= 10:
        p["reflection_depth"]  = _nudge(p["reflection_depth"],  +0.5)

    _save_personality(user_id, p)
    return p


# --------------------------------------------------
# Prompt block
# --------------------------------------------------

def personality_prompt_block(p: dict[str, float]) -> str:
    """
    Chuyển personality profile thành hướng dẫn tự nhiên cho AI.
    Không inject raw numbers — chuyển thành ngôn ngữ hành vi.
    """
    lines = []

    # Empathy
    if p["empathy_level"] >= 0.8:
        lines.append("Ưu tiên đồng cảm sâu — phản chiếu cảm xúc là trung tâm.")
    elif p["empathy_level"] <= 0.4:
        lines.append("Giữ giọng bình tĩnh — không cần biểu cảm nhiều.")

    # Question frequency
    if p["question_frequency"] >= 0.7:
        lines.append("User thích được hỏi — đặt câu hỏi mở khi tự nhiên.")
    elif p["question_frequency"] <= 0.3:
        lines.append("Hạn chế hỏi — chủ yếu lắng nghe và phản chiếu.")

    # Reflection depth
    if p["reflection_depth"] >= 0.7:
        lines.append("Phản chiếu sâu — khai thác lớp ý nghĩa phía dưới.")
    elif p["reflection_depth"] <= 0.3:
        lines.append("Phản chiếu nhẹ — đừng đào quá sâu.")

    # Guidance strength
    if p["guidance_strength"] >= 0.6:
        lines.append("User đang tìm hướng — có thể gợi ý nhẹ khi phù hợp.")
    else:
        lines.append("Tránh đưa hướng dẫn trừ khi user hỏi trực tiếp.")

    # Warmth
    if p["warmth_level"] >= 0.8:
        lines.append("Giọng rất ấm — như người thân thiết ngồi cạnh.")
    elif p["warmth_level"] <= 0.4:
        lines.append("Giữ giọng bình tĩnh, không quá thân mật.")

    if not lines:
        return ""
    return "Phong cách thích nghi với user này:\n" + "\n".join(f"- {l}" for l in lines)
