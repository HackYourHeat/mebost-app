# --------------------------------------------------
# Intent Engine — MEBOST Hải Đăng V1.2
# V1.2: mở rộng "help" patterns — bắt được các cách
#       xin lời khuyên trực tiếp bằng cả tiếng Việt + Anh.
#       "help" được ưu tiên cao hơn "question".
# --------------------------------------------------

VALID_INTENTS = {"talk", "question", "help", "vent", "reflection", "exploration"}

# keyword list → intent
# Thứ tự quan trọng: match đầu tiên thắng.
# "help" phải đứng TRƯỚC "question" vì nhiều câu xin lời khuyên có dấu ?
_RULES: list[tuple[list[str], str]] = [
    (
        # Help / advice — bắt rộng, ưu tiên cao nhất (thêm V1.3)
        [
            "khuyên tôi", "khuyên mình", "khuyên tao",
            "lời khuyên", "cho tôi lời khuyên", "cho mình lời khuyên",
            "hãy khuyên", "bạn khuyên", "anh khuyên", "chị khuyên",
            "nên làm gì", "nên làm gì bây giờ", "phải làm gì",
            "tôi nên làm", "mình nên làm", "tao nên làm",
            "hướng giải quyết", "cách giải quyết",
            "giúp tôi cụ thể", "giúp mình cụ thể",
            "nói tôi nên", "nói mình nên",
            "chỉ tôi", "chỉ mình",
            "hãy chỉ",
            "giúp tôi với", "giúp mình với", "giúp tao với",
            "tôi cần lời khuyên", "mình cần lời khuyên",
            "cho tôi vài điều", "cho mình vài điều",
            "làm ơn giúp", "làm ơn nói",
            # English
            "give me advice", "advise me", "help me with",
            # V1.3 additions
            "khuyên tôi", "khuyên mình", "lời khuyên",
            "cho tôi lời khuyên", "cho mình lời khuyên",
            "hãy khuyên", "hãy chỉ", "chỉ cho tôi", "chỉ cho mình",
            "hướng giải quyết", "nói tôi nên làm gì", "nói mình nên làm gì",
            "cho tôi vài điều", "giúp tôi cụ thể", "giúp mình cụ thể",
            "tôi cần lời khuyên", "mình cần lời khuyên",
            "what should i do", "tell me what to do", "what do i do",
            "give me something", "just tell me",
            "what should i do", "tell me what to do", "what do i do",
            "what can i do", "how do i", "help me figure",
            "give me a suggestion", "suggest something",
        ],
        "help",
    ),
    (
        # Vent — muốn trút, không cần giải
        [
            "mình chỉ muốn nói", "chỉ muốn kể", "chỉ muốn tâm sự",
            "vent", "xả", "trút", "tâm sự thôi", "than thôi",
            "không cần giải pháp", "chỉ cần ai nghe",
            "just want to vent", "just need to talk",
        ],
        "vent",
    ),
    (
        # Reflection / exploration
        [
            "nghĩ lại", "nhìn lại", "hiểu bản thân",
            "reflect", "understand myself", "ý nghĩa", "meaning",
            "khám phá", "explore",
        ],
        "reflection",
    ),
    (
        # Question — sau help vì nhiều help-question có dấu ?
        [
            "tại sao", "why", "how", "làm sao", "làm thế nào",
            "?", "what", "khi nào", "bao giờ",
        ],
        "question",
    ),
]

_FALLBACK = "talk"

# Từ khóa phát hiện user phàn nàn AI không giúp / chỉ hỏi ngược
# → trigger chuyển mode sang engage
_FRUSTRATION_PATTERNS = [
    "bạn cứ hỏi", "bạn không giúp", "bạn chỉ hỏi",
    "cứ hỏi ngược", "hỏi ngược lại", "không giúp gì",
    "tại sao bạn im", "bạn im lặng", "không nói gì",
    "không có ích", "chả giúp được", "vô ích",
    "you keep asking", "you're not helping", "just answer me",
    "stop asking", "don't ask me",
]


def detect_intent(text: str) -> str:
    lower = text.lower()

    # Check frustration trước — override intent thành "help" để unlock advice
    if any(p in lower for p in _FRUSTRATION_PATTERNS):
        return "help"

    for keywords, intent in _RULES:
        if any(kw in lower for kw in keywords):
            return intent

    return _FALLBACK


def is_frustrated(text: str) -> bool:
    """True nếu user đang phàn nàn AI không giúp / chỉ hỏi ngược."""
    lower = text.lower()
    return any(p in lower for p in _FRUSTRATION_PATTERNS)


def normalize_intent(label: str) -> str:
    return label if label in VALID_INTENTS else _FALLBACK


def intent_hint(label: str) -> str:
    return f"Intent hint: {normalize_intent(label)}"


def build_intent_context(text: str) -> dict:
    label     = detect_intent(text)
    label     = normalize_intent(label)
    frustrated = is_frustrated(text)

    return {
        "intent":     label,
        "hint":       intent_hint(label),
        "frustrated": frustrated,   # flag cho response_strategy_engine
    }
