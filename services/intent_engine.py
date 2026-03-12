# --------------------------------------------------
# Intent Engine — MEBOST Hải Đăng
# V1: keyword-based detection
# --------------------------------------------------

VALID_INTENTS = {"talk", "question", "help", "vent", "reflection"}

# keyword list → intent  (thứ tự = priority, match đầu tiên thắng)
_RULES: list[tuple[list[str], str]] = [
    (
        ["giúp", "help", "advice", "lời khuyên", "nên làm gì", "what should i do"],
        "help",
    ),
    (
        ["tại sao", "why", "how", "làm sao", "?", "what", "khi nào", "bao giờ"],
        "question",
    ),
    (
        ["mình chỉ muốn nói", "vent", "xả", "trút", "tâm sự", "than thôi", "chỉ muốn kể"],
        "vent",
    ),
    (
        ["nghĩ", "reflect", "understand", "hiểu", "khám phá", "nhìn lại", "ý nghĩa", "meaning"],
        "reflection",
    ),
]

_FALLBACK = "talk"


# --------------------------------------------------
# Core functions
# --------------------------------------------------

def detect_intent(text: str) -> str:
    """
    Phát hiện intent từ text bằng keyword matching.
    Match đầu tiên trong _RULES thắng.

    Returns:
        intent_label
    """
    lower = text.lower()

    for keywords, intent in _RULES:
        if any(kw in lower for kw in keywords):
            return intent

    return _FALLBACK


def normalize_intent(label: str) -> str:
    """
    Đảm bảo intent label nằm trong tập hợp lệ.
    Trả về 'talk' nếu label không hợp lệ.
    """
    return label if label in VALID_INTENTS else _FALLBACK


def intent_hint(label: str) -> str:
    """
    Tạo intent hint string cho prompt builder.

    Example: "Intent hint: reflection"
    """
    return f"Intent hint: {normalize_intent(label)}"


def build_intent_context(text: str) -> dict:
    """
    Pipeline đầy đủ: text → intent context dict.

    Returns:
        {
            "intent": str,
            "hint":   str,
        }
    """
    label = detect_intent(text)
    label = normalize_intent(label)

    return {
        "intent": label,
        "hint":   intent_hint(label),
    }
