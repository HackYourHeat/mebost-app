# --------------------------------------------------
# Adaptive Tone Engine — MEBOST V1.3
# --------------------------------------------------
# Học cách user muốn được lắng nghe từ feedback.
# Chỉ thay đổi style — không thay đổi core safety rules.
# --------------------------------------------------

from __future__ import annotations
import re
from db import get_db, utc_now_iso

# --------------------------------------------------
# Defaults
# --------------------------------------------------

TONE_DEFAULTS = {
    "reply_length":      "medium",
    "reflection_level":  "medium",
    "question_style":    "gentle",
    "advice_style":      "ask_first",
    "warmth_level":      "warm",
}

# --------------------------------------------------
# Simple keyword rules — extract tone signals từ feedback user
# --------------------------------------------------

_RULES: list[tuple[list[str], str, str]] = [
    # (keywords, field, value)
    (["dài quá", "ngắn lại", "quá dài", "nói ít thôi"],             "reply_length",     "short"),
    (["ngắn quá", "nói nhiều hơn", "chi tiết hơn"],                  "reply_length",     "long"),
    (["thích khi bạn hỏi", "hỏi lại", "hỏi thêm"],                   "question_style",   "open"),
    (["đừng hỏi nhiều", "hỏi ít thôi"],                               "question_style",   "minimal"),
    (["đừng khuyên", "đừng vội khuyên", "không cần lời khuyên"],      "advice_style",     "ask_first"),
    (["có thể gợi ý", "cho mình lời khuyên", "hướng dẫn mình"],      "advice_style",     "offer"),
    (["nói sâu hơn", "sâu hơn", "phân tích hơn"],                     "reflection_level", "high"),
    (["nhẹ thôi", "không cần sâu"],                                    "reflection_level", "low"),
    (["ấm hơn", "thân hơn", "gần gũi hơn"],                           "warmth_level",     "very_warm"),
    (["bình thường thôi", "không cần quá thân"],                       "warmth_level",     "neutral"),
]


def extract_tone_signals(text: str) -> dict[str, str]:
    """
    Quét text feedback → trả dict {field: new_value}.
    Ví dụ: "bạn nói dài quá" → {"reply_length": "short"}
    """
    text_lower = text.lower()
    updates: dict[str, str] = {}
    for keywords, field, value in _RULES:
        if any(kw in text_lower for kw in keywords):
            updates[field] = value
    return updates


# --------------------------------------------------
# DB helpers
# --------------------------------------------------

def get_tone_profile(user_id: str) -> dict[str, str]:
    """Lấy tone profile. Trả defaults nếu chưa có."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM user_tone_profile WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()
        if row:
            return {
                "reply_length":     row["reply_length"]     or TONE_DEFAULTS["reply_length"],
                "reflection_level": row["reflection_level"] or TONE_DEFAULTS["reflection_level"],
                "question_style":   row["question_style"]   or TONE_DEFAULTS["question_style"],
                "advice_style":     row["advice_style"]     or TONE_DEFAULTS["advice_style"],
                "warmth_level":     row["warmth_level"]     or TONE_DEFAULTS["warmth_level"],
            }
    except Exception:
        pass
    return dict(TONE_DEFAULTS)


def update_tone_profile(user_id: str, updates: dict[str, str]) -> bool:
    """Merge updates vào tone profile. Chỉ update fields được cung cấp."""
    if not updates:
        return False
    current = get_tone_profile(user_id)
    current.update(updates)
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_tone_profile
               (user_id, reply_length, reflection_level, question_style,
                advice_style, warmth_level, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 reply_length      = excluded.reply_length,
                 reflection_level  = excluded.reflection_level,
                 question_style    = excluded.question_style,
                 advice_style      = excluded.advice_style,
                 warmth_level      = excluded.warmth_level,
                 updated_at        = excluded.updated_at""",
            (
                user_id,
                current["reply_length"],
                current["reflection_level"],
                current["question_style"],
                current["advice_style"],
                current["warmth_level"],
                utc_now_iso(),
            ),
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


# --------------------------------------------------
# Prompt block
# --------------------------------------------------

def tone_profile_prompt_block(profile: dict[str, str]) -> str:
    """Inject tone profile vào system prompt."""
    length_hint = {
        "short":  "Trả lời ngắn — tối đa 2–3 đoạn.",
        "medium": "Trả lời vừa phải — 3–5 đoạn tùy ngữ cảnh.",
        "long":   "Trả lời đầy đủ hơn khi phù hợp — tối đa 6 đoạn.",
    }.get(profile.get("reply_length", "medium"), "")

    reflection_hint = {
        "low":    "Phản chiếu nhẹ — không đào sâu quá.",
        "medium": "Phản chiếu cân bằng.",
        "high":   "Phản chiếu sâu — đặt câu hỏi mở rộng góc nhìn.",
    }.get(profile.get("reflection_level", "medium"), "")

    question_hint = {
        "gentle":   "Câu hỏi nhẹ, không áp lực.",
        "open":     "Ưu tiên câu hỏi mở để user nói nhiều hơn.",
        "minimal":  "Hạn chế hỏi — chủ yếu lắng nghe và phản chiếu.",
    }.get(profile.get("question_style", "gentle"), "")

    advice_hint = {
        "ask_first": "Không đưa lời khuyên trừ khi user hỏi.",
        "offer":     "Có thể gợi ý nhẹ khi tự nhiên.",
    }.get(profile.get("advice_style", "ask_first"), "")

    warmth_hint = {
        "neutral":   "Giữ giọng bình tĩnh, không quá thân mật.",
        "warm":      "Giọng ấm áp, gần gũi.",
        "very_warm": "Giọng rất ấm, như người thân thiết.",
    }.get(profile.get("warmth_level", "warm"), "")

    lines = [h for h in [length_hint, reflection_hint, question_hint, advice_hint, warmth_hint] if h]
    if not lines:
        return ""
    return "Tone preferences của user:\n" + "\n".join(f"- {l}" for l in lines)
