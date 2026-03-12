# --------------------------------------------------
# Emotion Engine — MEBOST Hải Đăng V1.1 (Hybrid)
# --------------------------------------------------

import re

_VALID_EMOTIONS = {"sad", "anxious", "tired", "angry", "happy", "neutral"}

# --------------------------------------------------
# Keyword maps
# --------------------------------------------------

_KEYWORD_MAP = {
    "sad": [
        "buồn", "khóc", "nhớ", "cô đơn", "trống", "mất mát", "đau lòng",
        "tuyệt vọng", "chán nản", "thất vọng", "sad", "cry", "lonely",
        "miss", "hurt", "heartbreak", "grief", "hopeless",
    ],
    "anxious": [
        "lo", "lo lắng", "sợ", "hồi hộp", "bất an", "lo âu", "căng thẳng",
        "stress", "áp lực", "worried", "anxious", "afraid", "nervous",
        "uneasy", "panic", "fear",
    ],
    "tired": [
        "mệt", "kiệt sức", "nặng nề", "uể oải", "mệt mỏi", "không còn sức",
        "tired", "exhausted", "drained", "heavy", "burned out", "weary",
    ],
    "angry": [
        "tức", "giận", "bực", "bực bội", "phẫn nộ", "angry", "mad",
        "annoyed", "furious", "rage", "upset", "frustrated",
    ],
    "happy": [
        "vui", "hạnh phúc", "phấn khởi", "tốt", "ổn", "tuyệt", "hào hứng",
        "happy", "joy", "great", "excited", "proud", "love", "wonderful",
    ],
}

_AMBIGUOUS_SIGNALS = [
    r"vừa.*vừa", r"nhưng.*lại", r"dù.*vẫn",
    r"both.*and", r"although.*still",
]


# --------------------------------------------------
# Public interface (giữ nguyên từ V1)
# --------------------------------------------------

def detect_emotion(text: str) -> tuple[str, int]:
    """
    Hybrid detection:
    - Keyword scan trước.
    - Nếu message dài / mơ hồ / neutral → thử LLM classifier.
    Trả về (emotion_label, intensity).
    """
    label, intensity = _keyword_detect(text)
    stripped = text.strip()

    # Điều kiện gọi LLM
    should_use_llm = (
        len(stripped) >= 80
        or label == "neutral"
        or _is_ambiguous(stripped)
    )

    if should_use_llm:
        result = _llm_detect_emotion(stripped)
        if result:
            label     = normalize_emotion(result["emotion"])
            intensity = result["intensity"]

    return label, intensity


def normalize_emotion(label: str) -> str:
    label = str(label or "").lower().strip()
    return label if label in _VALID_EMOTIONS else "neutral"


def emotion_hint(label: str, intensity: int) -> str:
    return f"Emotion hint: {label} (intensity {intensity})"


def build_emotion_context(text: str) -> dict:
    label, intensity = detect_emotion(text)
    return {
        "emotion":   label,
        "intensity": intensity,
        "hint":      emotion_hint(label, intensity),
    }


# --------------------------------------------------
# Private — keyword detection
# --------------------------------------------------

def _keyword_detect(text: str) -> tuple[str, int]:
    low    = text.lower()
    scores = {e: 0 for e in _KEYWORD_MAP}

    for emotion, keywords in _KEYWORD_MAP.items():
        for kw in keywords:
            if kw in low:
                scores[emotion] += 1

    best  = max(scores, key=lambda e: scores[e])
    score = scores[best]

    if score == 0:
        return "neutral", 5

    # intensity từ keyword count
    intensity = min(10, 3 + score * 2)
    return best, intensity


def _is_ambiguous(text: str) -> bool:
    """Phát hiện tín hiệu cảm xúc lẫn lộn."""
    for pattern in _AMBIGUOUS_SIGNALS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


# --------------------------------------------------
# Private — LLM classifier
# --------------------------------------------------

def _llm_detect_emotion(text: str) -> dict | None:
    """
    Gọi LLM nhẹ để detect emotion.
    Fallback về None nếu lỗi.
    """
    try:
        from services.llm_adapter import classify_emotion_llm
        return classify_emotion_llm(text)
    except Exception:
        return None
