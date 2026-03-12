# --------------------------------------------------
# Listening Style Service — MEBOST V1.3
# --------------------------------------------------
# 3 styles: quiet_listener | gentle_companion | reflective_guide
# --------------------------------------------------

from __future__ import annotations
from db import get_db, utc_now_iso

VALID_STYLES   = {"quiet_listener", "gentle_companion", "reflective_guide"}
DEFAULT_STYLE  = "gentle_companion"

# Prompt blocks injected into system prompt
_STYLE_BLOCKS: dict[str, str] = {
    "quiet_listener": (
        "Listening style: quiet_listener\n"
        "- Phản chiếu cảm xúc thuần túy — không khuyên.\n"
        "- Câu hỏi nhẹ, sâu, chỉ một câu mỗi lượt.\n"
        "- Ngồi im và lắng nghe nhiều hơn nói."
    ),
    "gentle_companion": (
        "Listening style: gentle_companion\n"
        "- Phản chiếu ấm áp, cân bằng.\n"
        "- Hỏi mở để user mở lòng thêm.\n"
        "- Thỉnh thoảng gợi ý nhẹ nếu tự nhiên."
    ),
    "reflective_guide": (
        "Listening style: reflective_guide\n"
        "- Đặt câu hỏi sâu hơn, mở rộng góc nhìn.\n"
        "- Phân tích nhẹ, không áp đặt.\n"
        "- Gợi ý góc nhìn mới khi phù hợp."
    ),
}


def get_listening_style(user_id: str) -> str:
    """Lấy listening style của user. Default: gentle_companion."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT listening_style FROM user_preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row and row["listening_style"] in VALID_STYLES:
            return row["listening_style"]
    except Exception:
        pass
    return DEFAULT_STYLE


def set_listening_style(user_id: str, style: str) -> bool:
    """Lưu listening style. Trả False nếu style không hợp lệ."""
    if style not in VALID_STYLES:
        return False
    try:
        db  = get_db()
        db.execute(
            """INSERT INTO user_preferences (user_id, listening_style, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 listening_style = excluded.listening_style,
                 updated_at = excluded.updated_at""",
            (user_id, style, utc_now_iso()),
        )
        db.commit()
        db.close()
        return True
    except Exception:
        return False


def listening_style_prompt_block(style: str) -> str:
    """Trả về đoạn prompt inject vào system prompt."""
    return _STYLE_BLOCKS.get(style, _STYLE_BLOCKS[DEFAULT_STYLE])
