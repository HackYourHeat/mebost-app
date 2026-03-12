# --------------------------------------------------
# Familiarity Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Tạo cảm giác "quen lâu rồi" — không phải AI gặp lần đầu.
#
# Khác với trust (an toàn trong quan hệ) và
# relational_continuity (narrative arc):
#   familiarity = cảm giác thân quen theo thời gian
#   → ảnh hưởng đến *cách nói*, không phải *mức độ sâu*
#
# 4 levels: new → warming → familiar → trusted
#
# Output inject vào prompt builder:
#   familiarity_level       — mức thân quen
#   callback_probability    — xác suất nhắc lại điều cũ
#   tone_relaxation         — AI có thể bớt formal
#   shared_history_weight   — mức độ tham chiếu lịch sử
#
# Không gọi LLM. Không tạo bảng mới.
# Đọc từ messages, user_internal_state, trust đã có.
# Fail-safe: luôn trả default nếu lỗi.
# --------------------------------------------------

from __future__ import annotations

from db import get_db

# --------------------------------------------------
# Thresholds
# --------------------------------------------------

# (total_messages_threshold, trust_threshold) → level
_LEVEL_RULES: list[tuple[int, float, str]] = [
    (120, 0.70, "trusted"),
    (50,  0.55, "familiar"),
    (20,  0.40, "warming"),
    (0,   0.00, "new"),
]

# Per-level behavior weights
_LEVEL_CONFIG: dict[str, dict] = {
    "new": {
        "callback_probability":  0.00,
        "tone_relaxation":       0.00,
        "shared_history_weight": 0.00,
    },
    "warming": {
        "callback_probability":  0.20,
        "tone_relaxation":       0.15,
        "shared_history_weight": 0.20,
    },
    "familiar": {
        "callback_probability":  0.50,
        "tone_relaxation":       0.40,
        "shared_history_weight": 0.55,
    },
    "trusted": {
        "callback_probability":  0.75,
        "tone_relaxation":       0.65,
        "shared_history_weight": 0.80,
    },
}


# --------------------------------------------------
# Public API
# --------------------------------------------------

def compute_familiarity(
    user_id: str,
    trust: float = 0.30,
    relationship_days: int = 0,
    momentum: float = 0.0,
) -> dict:
    """
    Tính familiarity state từ lịch sử messages + trust.
    Không bao giờ raise.
    """
    try:
        total_msgs = _get_total_messages(user_id)
        level      = _infer_level(total_msgs, trust)
        config     = _LEVEL_CONFIG[level]

        # Bonus nhỏ từ relationship_days (tích luỹ thêm)
        day_bonus  = min(relationship_days / 90.0, 0.10)

        return {
            "familiarity_level":      level,
            "total_messages":         total_msgs,
            "callback_probability":   round(min(1.0, config["callback_probability"] + day_bonus * 0.5), 3),
            "tone_relaxation":        round(min(1.0, config["tone_relaxation"] + day_bonus * 0.3),      3),
            "shared_history_weight":  round(min(1.0, config["shared_history_weight"] + day_bonus * 0.4),3),
        }
    except Exception:
        return _default_familiarity()


def familiarity_prompt_block(fam: dict) -> str:
    """
    Chuyển familiarity state → hướng dẫn cụ thể cho LLM.
    Ngắn, behavioral, không lặp với trust/temporal block.
    """
    level = fam.get("familiarity_level", "new")
    cb    = fam.get("callback_probability", 0.0)
    relax = fam.get("tone_relaxation", 0.0)

    if level == "new":
        return (
            "Lần đầu gặp — thận trọng, ấm áp nhưng không tạo cảm giác gượng ép.\n"
            "Chưa đề cập đến lịch sử hay ký ức cũ."
        )

    lines = []

    if level == "warming":
        lines.append("Đang xây dựng quen biết — nhẹ nhàng, chưa thân nhiều.")
        if cb >= 0.15:
            lines.append("Có thể nhắc lại điều user đã chia sẻ rất nhẹ nếu tự nhiên.")

    elif level == "familiar":
        lines.append("User và Hải Đăng đã có lịch sử chung.")
        if cb >= 0.40:
            lines.append("Có thể tham chiếu điều đã chia sẻ trước đây một cách tự nhiên.")
        if relax >= 0.35:
            lines.append("Giọng điệu có thể thoải mái hơn — bớt formal, gần hơn.")

    elif level == "trusted":
        lines.append("Quan hệ dài — user cảm thấy được biết đến.")
        if cb >= 0.60:
            lines.append("Có thể nhắc lại tự nhiên — như người bạn nhớ chuyện của nhau.")
        if relax >= 0.55:
            lines.append("Giọng ấm và gần — khoảng cách đã được rút ngắn qua thời gian.")

    lines.append(_callback_instruction(level, cb))

    return "\n".join(l for l in lines if l)


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _get_total_messages(user_id: str) -> int:
    """Đếm tổng messages của user (user + assistant)."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _infer_level(total_msgs: int, trust: float) -> str:
    """
    Deterministic: chọn level cao nhất mà cả 2 threshold đều đạt.
    """
    for msg_thresh, trust_thresh, level in _LEVEL_RULES:
        if total_msgs >= msg_thresh and trust >= trust_thresh:
            return level
    return "new"


def _callback_instruction(level: str, cb: float) -> str:
    """Tạo instruction cụ thể về callback references."""
    if level == "new" or cb < 0.15:
        return ""
    if level == "warming":
        return (
            "Nếu nhắc lại: dùng 'Trước đây bạn có đề cập…' — rất nhẹ, không ép."
        )
    if level == "familiar":
        return (
            "Nếu nhắc lại: tự nhiên như 'Lần trước mình nói chuyện về…' "
            "hoặc 'Hình như chủ đề này đã từng ở đây rồi.'"
        )
    if level == "trusted":
        return (
            "Nếu nhắc lại: thoải mái như người bạn — "
            "'Mình nhớ bạn đã kể chuyện đó…' — không cần rào đón."
        )
    return ""


def _default_familiarity() -> dict:
    return {
        "familiarity_level":     "new",
        "total_messages":        0,
        "callback_probability":  0.0,
        "tone_relaxation":       0.0,
        "shared_history_weight": 0.0,
    }
