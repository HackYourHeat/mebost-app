# --------------------------------------------------
# User State Inference Engine — MEBOST V1.4
# --------------------------------------------------
# Ước lượng trạng thái nội tâm user từ tín hiệu ngôn ngữ.
#
# Pipeline:
#   message → signal_extraction → internal_state → prompt_hint
# --------------------------------------------------

from __future__ import annotations
import math

# --------------------------------------------------
# Signal extraction — keyword patterns
# --------------------------------------------------

_DISTRESS_PATTERNS = [
    "không chịu được", "mệt quá", "sợ", "hoảng", "tệ lắm", "khổ",
    "kiệt sức", "không thở được", "muốn khóc", "đau lòng", "tuyệt vọng",
    "không còn sức", "chán", "exhausted", "overwhelmed", "scared", "terrified",
]
_SAFETY_PATTERNS = [
    "ổn hơn rồi", "đỡ hơn", "cảm ơn", "bình tĩnh", "nhẹ hơn",
    "hiểu rồi", "thấy được", "cảm thấy an", "better", "calm", "relieved",
]
_OVERLOAD_PATTERNS = [
    "không biết bắt đầu từ đâu", "rối quá", "quá nhiều thứ", "không xử lý được",
    "đầu óc trống", "tràn ngập", "overwhelming", "too much", "confusing",
    "đủ thứ", "lung tung",
]
_SALIENCE_PATTERNS = [
    "quan trọng", "điều này", "vấn đề là", "mấu chốt", "bản chất",
    "thật ra", "sự thật là", "cốt lõi", "important", "the thing is", "basically",
]
_CLARITY_PATTERNS = [
    "rõ ràng", "mình hiểu", "đúng rồi", "nhận ra", "thấy rõ",
    "aha", "makes sense", "I see", "clear", "got it",
]
_HELP_SEEKING_PATTERNS = [
    "giúp mình", "mình cần", "bạn nghĩ sao", "làm sao", "phải làm gì",
    "hướng dẫn", "help me", "what should", "can you", "advice",
]


def _score(text: str, patterns: list[str]) -> float:
    """0.0–1.0 dựa trên số pattern match / tổng patterns."""
    text_lower = text.lower()
    hits = sum(1 for p in patterns if p in text_lower)
    return min(hits / max(len(patterns) * 0.15, 1), 1.0)


def extract_signals(message: str) -> dict[str, float]:
    """
    Trả về dict signals từ 0.0 đến 1.0.

    Keys: distress, safety, overload, salience, clarity, help_seeking
    """
    return {
        "distress":     round(_score(message, _DISTRESS_PATTERNS), 2),
        "safety":       round(_score(message, _SAFETY_PATTERNS), 2),
        "overload":     round(_score(message, _OVERLOAD_PATTERNS), 2),
        "salience":     round(_score(message, _SALIENCE_PATTERNS), 2),
        "clarity":      round(_score(message, _CLARITY_PATTERNS), 2),
        "help_seeking": round(_score(message, _HELP_SEEKING_PATTERNS), 2),
    }


# --------------------------------------------------
# Internal state model (neuro-inspired)
# --------------------------------------------------

_DEFAULT_INTERNAL: dict[str, float] = {
    "arousal":  0.0,
    "calm":     0.5,
    "pressure": 0.0,
    "trust":    0.3,
    "depth":    0.0,
}

_DECAY = 0.15   # pressure decay mỗi turn


def update_internal_state(
    signals: dict[str, float],
    previous: dict[str, float] | None = None,
) -> dict[str, float]:
    """
    Cập nhật internal state từ signals.

    Rules:
      distress  → pressure tăng, calm giảm
      safety    → calm tăng, pressure giảm
      overload  → arousal tăng, depth giảm
      salience  → depth tăng
      clarity   → calm tăng nhẹ
      help_seeking → trust tăng nhẹ

    Pressure decay: giảm _DECAY mỗi turn (bình thường hoá dần).
    """
    s = dict(previous) if previous else dict(_DEFAULT_INTERNAL)

    # Decay pressure trước
    s["pressure"] = max(0.0, s["pressure"] - _DECAY)

    # Apply signals
    s["pressure"] += signals["distress"] * 0.5
    s["pressure"] -= signals["safety"]   * 0.3
    s["calm"]     += signals["safety"]   * 0.4
    s["calm"]     -= signals["distress"] * 0.3
    s["arousal"]  += signals["overload"] * 0.4
    s["depth"]    += signals["salience"] * 0.3
    s["depth"]    -= signals["overload"] * 0.1
    s["calm"]     += signals["clarity"]  * 0.2
    s["trust"]    += signals["help_seeking"] * 0.1

    # Clamp all values [0, 1]
    for k in s:
        s[k] = round(min(1.0, max(0.0, s[k])), 2)

    return s


# --------------------------------------------------
# Expression modulation
# --------------------------------------------------

def expression_hint(state: dict[str, float]) -> str:
    """
    Trả về hint cho prompt dựa trên internal state.
    """
    hints = []

    if state.get("pressure", 0) >= 0.6:
        hints.append("Áp lực nội tâm đang cao — câu ngắn, phản chiếu trước, không vội giải quyết.")
    elif state.get("pressure", 0) >= 0.35:
        hints.append("Áp lực vừa phải — ưu tiên lắng nghe, hạn chế lời khuyên.")

    if state.get("calm", 0) >= 0.6:
        hints.append("Không gian yên tĩnh — có thể nói chậm và sâu hơn.")

    if state.get("depth", 0) >= 0.5:
        hints.append("User đang suy ngẫm — đặt câu hỏi mở, không vội kết luận.")

    if state.get("trust", 0) >= 0.6:
        hints.append("Độ tin tưởng cao — có thể dùng memory tự nhiên nếu liên quan.")

    if state.get("arousal", 0) >= 0.6:
        hints.append("Tâm trí đang rối — không thêm thông tin, chỉ phản chiếu và neo lại.")

    if not hints:
        return ""
    return "Trạng thái nội tâm ước lượng:\n" + "\n".join(f"- {h}" for h in hints)
