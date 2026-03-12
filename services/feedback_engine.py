# --------------------------------------------------
# Feedback Engine — MEBOST V1.3
# --------------------------------------------------
# Hải Đăng hỏi user mỗi 7 AI messages:
#   "Mình nói vậy có gần với điều bạn đang cảm thấy không?"
# Feedback được lưu + dùng để cập nhật tone profile.
# --------------------------------------------------

from __future__ import annotations
import random
from db import get_db, utc_now_iso

FEEDBACK_EVERY_N = 7   # hỏi sau mỗi N AI messages

# Câu hỏi feedback — ngẫu nhiên để tránh lặp
_FEEDBACK_PROMPTS_VI = [
    "\n\n*Mình nói vậy có gần với điều bạn đang cảm thấy không?*",
    "\n\n*Cách mình phản hồi có khiến bạn thấy được lắng nghe không?*",
    "\n\n*Bạn muốn mình lắng nghe nhiều hơn hay gợi ý nhiều hơn?*",
    "\n\n*Có điều gì bạn muốn mình hiểu khác đi không?*",
]

_FEEDBACK_PROMPTS_EN = [
    "\n\n*Does that feel close to what you're experiencing?*",
    "\n\n*Did my response make you feel heard?*",
    "\n\n*Would you prefer I listen more, or offer more suggestions?*",
    "\n\n*Is there anything you'd like me to understand differently?*",
]


def should_ask_feedback(user_id: str, session_id: str) -> bool:
    """True nếu đã đủ N AI messages từ lần feedback cuối."""
    try:
        db = get_db()

        # Đếm AI messages trong session
        total_ai = db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=? AND role='assistant'",
            (session_id,),
        ).fetchone()[0]

        # Lần feedback gần nhất
        last_fb = db.execute(
            """SELECT ai_message_id FROM conversation_feedback
               WHERE user_id=? AND session_id=?
               ORDER BY id DESC LIMIT 1""",
            (user_id, session_id),
        ).fetchone()
        db.close()

        if last_fb is None:
            return total_ai >= FEEDBACK_EVERY_N
        return (total_ai - last_fb["ai_message_id"]) >= FEEDBACK_EVERY_N
    except Exception:
        return False


def get_feedback_prompt(lang_key: str = "vi") -> str:
    pool = _FEEDBACK_PROMPTS_VI if lang_key == "vi" else _FEEDBACK_PROMPTS_EN
    return random.choice(pool)


def save_feedback_prompt(
    user_id: str, session_id: str, ai_message_id: int, feedback_text: str
) -> None:
    """Lưu câu hỏi feedback đã gửi."""
    try:
        db = get_db()
        db.execute(
            """INSERT INTO conversation_feedback
               (user_id, session_id, ai_message_id, feedback_text, created_at)
               VALUES (?,?,?,?,?)""",
            (user_id, session_id, ai_message_id, feedback_text, utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def count_ai_messages(session_id: str) -> int:
    """Đếm số AI messages trong session."""
    try:
        db  = get_db()
        cnt = db.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=? AND role='assistant'",
            (session_id,),
        ).fetchone()[0]
        db.close()
        return cnt
    except Exception:
        return 0
