# --------------------------------------------------
# Response Policy Engine — MEBOST Hải Đăng V1.2
# Thêm trigger deep_reflection khi message dài.
# --------------------------------------------------

# Ngưỡng kích hoạt deep reflection dựa trên độ dài message
LONG_MESSAGE_THRESHOLD = 600


def choose_response_policy(
    emotion_label: str,
    intensity: int,
    intent_label: str,
    message_len: int = 0,
    momentum: float = 0.0,
    trust: float = 0.30,
    gravity: float = 0.0,
) -> dict:
    """
    Chọn policy phản hồi dựa trên cảm xúc + intent + độ dài message.

    Args:
        message_len : len(message) — nếu >= LONG_MESSAGE_THRESHOLD → ưu tiên deep_reflection

    Returns:
        dict với keys: mode, reply_style, advice_allowed, base_variance
    """
    # A. Cảm xúc nặng → reflect trước
    if emotion_label in ("sad", "anxious", "angry") and intensity >= 7:
        return {
            "mode":           "reflect_first",
            "reply_style":    "gentle_short",
            "advice_allowed": False,
            "base_variance":  "low",
        }

    # B. Vent → chỉ lắng nghe
    if intent_label == "vent":
        return {
            "mode":           "listen_only",
            "reply_style":    "soft_reflective",
            "advice_allowed": False,
            "base_variance":  "low",
        }

    # C. Momentum + Trust → deep reflection chỉ khi cả hai đủ cao
    if (momentum >= 0.70 and trust >= 0.60) or (gravity >= 0.65 and trust >= 0.50):
        return {
            "mode":           "deep_reflection",
            "reply_style":    "slow_reflective",
            "advice_allowed": False,
            "base_variance":  "medium",
        }

    # D. Message dài → user đang tâm sự thật sự → deep reflection
    if message_len >= LONG_MESSAGE_THRESHOLD:
        return {
            "mode":           "deep_reflection",
            "reply_style":    "slow_reflective",
            "advice_allowed": False,
            "base_variance":  "medium",
        }

    # E. Cần giúp đỡ, cảm xúc nhẹ → có thể hướng dẫn nhẹ
    if intent_label == "help" and intensity < 7:
        return {
            "mode":           "supportive_help",
            "reply_style":    "gentle_guidance",
            "advice_allowed": True,
            "base_variance":  "medium",
        }

    # F. Muốn suy ngẫm
    if intent_label == "reflection":
        return {
            "mode":           "deep_reflection",
            "reply_style":    "slow_reflective",
            "advice_allowed": False,
            "base_variance":  "medium",
        }

    # G. Mặc định
    return {
        "mode":           "normal_companion",
        "reply_style":    "warm_balanced",
        "advice_allowed": False,
        "base_variance":  "medium",
    }


def policy_hint(policy: dict) -> str:
    """Tạo hint string để inject vào prompt."""
    allowed = "true" if policy["advice_allowed"] else "false"
    return (
        f"Response policy:\n"
        f"- mode: {policy['mode']}\n"
        f"- reply_style: {policy['reply_style']}\n"
        f"- advice_allowed: {allowed}"
    )
