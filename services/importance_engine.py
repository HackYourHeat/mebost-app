# --------------------------------------------------
# Importance Scoring Engine — MEBOST Hải Đăng
# V1: rule-based scoring
# --------------------------------------------------

# --------------------------------------------------
# Signal sets
# --------------------------------------------------

_HIGH_SIGNALS = [
    "hãy nhớ", "remember this",
    "gọi mình là", "call me",
    "tên mình là", "my name is",
    "điều này quan trọng", "this is important",
    "mục tiêu của mình", "my goal",
    "mình luôn", "i always",
    "mình thường", "i usually",
    "mình rất sợ", "i am very afraid",
    "mình đang lo", "i am worried",
    "không thích bị", "i do not like being",
]

_MEDIUM_SIGNALS = [
    "công việc", "career", "sự nghiệp",
    "gia đình", "family",
    "dự án", "project",
    "thất nghiệp", "unemployed",
    "relationship", "người yêu",
    "stress", "áp lực",
]

_LOW_VALUE_TOKENS = {"ok", "ừ", "haha", "hello", "test", "thanks", "cảm ơn"}

_MEMORY_THRESHOLD = 7


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def is_low_value_message(text: str) -> bool:
    """
    True nếu text thực chất chỉ là một cụm từ không đáng nhớ.
    So sánh sau khi strip + lowercase.
    """
    return text.strip().lower() in _LOW_VALUE_TOKENS


# --------------------------------------------------
# Scoring
# --------------------------------------------------

def score_importance(text: str, emotion_intensity: int) -> int:
    """
    Chấm điểm mức độ quan trọng của message.

    Rules:
        A. High signal match   → +4
        B. Medium signal match → +2
        C. Emotion intensity   → +2 / +1 / +0
        D. Message length > 120 chars → +1
        E. Low-value message → cap score tại 1

    Returns:
        int score clamped [0, 10]
    """
    # Low-value: cap sớm
    if is_low_value_message(text):
        return 1

    lower  = text.lower()
    score  = 0

    # A. High signals — stop at first match
    for signal in _HIGH_SIGNALS:
        if signal in lower:
            score += 4
            break

    # B. Medium signals — stop at first match
    for signal in _MEDIUM_SIGNALS:
        if signal in lower:
            score += 2
            break

    # C. Emotional weight
    if emotion_intensity >= 7:
        score += 2
    elif emotion_intensity >= 5:
        score += 1

    # D. Message length
    if len(text.strip()) > 120:
        score += 1

    return max(0, min(10, score))


# --------------------------------------------------
# Candidate gate
# --------------------------------------------------

def is_memory_candidate(score: int) -> bool:
    """True nếu score đủ ngưỡng để tạo memory node."""
    return score >= _MEMORY_THRESHOLD


# --------------------------------------------------
# Public API
# --------------------------------------------------

def build_importance_context(text: str, emotion_intensity: int) -> dict:
    """
    Pipeline đầy đủ: text + emotion_intensity → importance context.

    Returns:
        {
            "importance_score":    int,
            "is_memory_candidate": bool,
        }
    """
    score     = score_importance(text, emotion_intensity)
    candidate = is_memory_candidate(score)

    return {
        "importance_score":    score,
        "is_memory_candidate": candidate,
    }
