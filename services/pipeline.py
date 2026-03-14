"""
pipeline.py — MEBOST Hải Đăng V2.1 (Single Authority)

Mục tiêu của bản này:
- chỉ giữ MỘT authority quyết định phản hồi
- bỏ tư duy policy chồng lên strategy
- pipeline vẫn gọn: emotion → intent → strategy → memory → prompt → LLM

Trong runtime chính:
- authority quyết định phản hồi = select_strategy_with_reason()
- các engine khác nếu còn tồn tại chỉ là legacy / experimental
"""
from __future__ import annotations

# ── Emotion detection ──────────────────────────────────────────────────────

_EMOTION_MAP = {
    "sad": [
        "buồn", "khóc", "nhớ", "cô đơn", "trống", "mất mát", "tuyệt vọng",
        "sad", "cry", "lonely", "hurt", "heartbreak", "hopeless",
    ],
    "anxious": [
        "lo", "lo lắng", "sợ", "hồi hộp", "bất an", "căng thẳng",
        "stress", "áp lực", "worried", "anxious", "afraid", "panic",
    ],
    "tired": [
        "mệt", "kiệt sức", "nặng nề", "uể oải", "không còn sức",
        "tired", "exhausted", "drained", "burned out",
    ],
    "angry": [
        "tức", "giận", "bực", "phẫn nộ", "angry", "mad", "furious", "frustrated",
    ],
    "happy": [
        "vui", "hạnh phúc", "phấn khởi", "tuyệt", "hào hứng",
        "happy", "joy", "excited", "proud", "wonderful",
    ],
}


def detect_emotion(text: str) -> tuple[str, int]:
    lower = text.lower()
    scores = {emotion: 0 for emotion in _EMOTION_MAP}

    for emotion, keywords in _EMOTION_MAP.items():
        for kw in keywords:
            if kw in lower:
                scores[emotion] += 1

    best = max(scores, key=lambda e: scores[e])
    score = scores[best]
    if score == 0:
        return "neutral", 5
    return best, min(10, 3 + score * 2)


# ── Intent detection ───────────────────────────────────────────────────────

_HELP_SIGNALS = [
    "khuyên tôi", "khuyên mình", "lời khuyên", "nên làm gì", "phải làm gì",
    "hướng giải quyết", "giúp tôi cụ thể", "chỉ tôi", "chỉ mình",
    "giúp tôi với", "giúp mình với", "tôi cần lời khuyên",
    "give me advice", "advise me", "help me with", "what should i do",
    "tell me what to do", "what do i do", "how do i", "help me figure",
]
_VENT_SIGNALS = [
    "mình chỉ muốn nói", "chỉ muốn kể", "chỉ muốn tâm sự",
    "vent", "xả", "trút", "tâm sự thôi", "không cần giải pháp",
    "chỉ cần ai nghe", "just want to vent", "just need to talk",
]
_STUCK_SIGNALS = [
    "không biết phải làm gì", "không biết làm sao", "mình đang rối",
    "tôi đang rối", "i don't know what to do", "i'm lost", "i'm stuck",
    "không có hướng", "không biết bắt đầu từ đâu",
]
_FRUSTRATION_SIGNALS = [
    "bạn cứ hỏi", "bạn không giúp", "cứ hỏi ngược", "không giúp gì",
    "just answer", "stop asking", "you keep asking", "you're not helping",
]
_SELF_ATTACK_SIGNALS = [
    "vô dụng", "ăn bám", "thất bại rồi", "không xứng",
    "tôi vô dụng", "mình vô dụng", "tôi thật tệ", "mình thật tệ",
    "i'm worthless", "i'm useless", "i'm a failure", "i hate myself",
]


def detect_intent(text: str) -> str:
    lower = text.lower()
    if any(s in lower for s in _FRUSTRATION_SIGNALS):
        return "frustrated"
    if any(s in lower for s in _SELF_ATTACK_SIGNALS):
        return "self_attack"
    if any(s in lower for s in _HELP_SIGNALS):
        return "help"
    if any(s in lower for s in _STUCK_SIGNALS):
        return "stuck"
    if any(s in lower for s in _VENT_SIGNALS):
        return "vent"
    if "?" in text:
        return "question"
    return "talk"


# ── Single response authority ──────────────────────────────────────────────

_STRATEGIES = {"reflect", "comfort", "guide", "engage", "reframe"}


def select_strategy_with_reason(
    message: str,
    intent: str,
    emotion: str,
    trust: float = 0.30,
) -> tuple[str, str]:
    """
    Authority duy nhất cho runtime chính.

    Priority:
      1. frustrated  -> engage
      2. self_attack -> comfort / reframe
      3. help/stuck  -> guide
      4. vent        -> reflect
      5. heavy emotion -> reflect
      6. question/talk -> reflect
    """
    low = message.lower()

    if any(s in low for s in _FRUSTRATION_SIGNALS) or intent == "frustrated":
        return "engage", "frustration with AI → engage"

    if any(s in low for s in _SELF_ATTACK_SIGNALS) or intent == "self_attack":
        if trust >= 0.60:
            return "reframe", f"self-attack + trust={trust:.2f} → reframe"
        return "comfort", f"self-attack + trust={trust:.2f} → comfort"

    if intent == "help":
        return "guide", "intent=help → guide"

    if intent == "stuck" or any(s in low for s in _STUCK_SIGNALS):
        return "guide", "stuck pattern → guide"

    if intent == "vent":
        return "reflect", "intent=vent → reflect"

    if emotion in ("sad", "anxious", "tired", "angry"):
        return "reflect", f"heavy emotion={emotion} → reflect"

    if intent == "question":
        return "reflect", "intent=question but no direct help signal → reflect first"

    return "reflect", "default → reflect"


def select_strategy(message: str, intent: str, emotion: str, trust: float = 0.30) -> str:
    strategy, _ = select_strategy_with_reason(message, intent, emotion, trust)
    return strategy


# ── Trust (conditional, every N turns) ────────────────────────────────────

_VULNERABILITY_SIGNALS = [
    "chưa nói với ai", "lần đầu mình kể", "mình cô đơn",
    "thật ra mình", "i've never told", "i'm scared", "honestly",
]
_GRATITUDE_SIGNALS = [
    "cảm ơn", "bạn hiểu mình", "thank you", "that helped",
]


def compute_trust_delta(text: str, emotion_intensity: int) -> float:
    lower = text.lower()
    delta = 0.0
    if any(s in lower for s in _VULNERABILITY_SIGNALS):
        delta += 0.08
    if any(s in lower for s in _GRATITUDE_SIGNALS):
        delta += 0.04
    if len(text) > 200 and emotion_intensity >= 6:
        delta += 0.03
    if len(text) < 20:
        delta -= 0.01
    return max(-0.05, min(0.10, delta))


def load_trust(user_id: str) -> float:
    try:
        from db import get_db
        db = get_db()
        row = db.execute(
            "SELECT trust FROM user_trust WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        return float(row["trust"]) if row else 0.30
    except Exception:
        return 0.30


def update_trust(user_id: str, delta: float) -> float:
    try:
        from db import get_db, utc_now_iso
        current = load_trust(user_id)
        new_trust = max(0.05, min(0.95, current + delta * 0.3))
        db = get_db()
        db.execute(
            """INSERT INTO user_trust (user_id, trust, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET trust = ?, updated_at = ?""",
            (user_id, new_trust, utc_now_iso(), new_trust, utc_now_iso()),
        )
        db.commit()
        db.close()
        return new_trust
    except Exception:
        return 0.30


# ── Pronoun (conditional) ─────────────────────────────────────────────────

_PRONOUN_MODES = {
    "tớ": ("tớ", "cậu"),
    "cậu": ("tớ", "cậu"),
    "tôi": ("tôi", "bạn"),
    "con ": ("cô", "con"),
    "cháu": ("bác", "cháu"),
}


def infer_pronoun(text: str) -> tuple[str, str] | None:
    lower = text.lower()
    for signal, pair in _PRONOUN_MODES.items():
        if signal in lower:
            return pair
    return None


def load_pronoun(user_id: str) -> tuple[str, str]:
    try:
        from db import get_db
        db = get_db()
        row = db.execute(
            "SELECT ai_pronoun, user_pronoun FROM user_pronoun_profile WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row:
            return row["ai_pronoun"], row["user_pronoun"]
        return "mình", "bạn"
    except Exception:
        return "mình", "bạn"


def save_pronoun(user_id: str, ai_p: str, user_p: str) -> None:
    try:
        from db import get_db, utc_now_iso
        db = get_db()
        db.execute(
            """INSERT INTO user_pronoun_profile (user_id, ai_pronoun, user_pronoun, source, updated_at)
               VALUES (?, ?, ?, 'inferred', ?)
               ON CONFLICT(user_id) DO UPDATE SET ai_pronoun=?, user_pronoun=?, updated_at=?""",
            (user_id, ai_p, user_p, utc_now_iso(), ai_p, user_p, utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def resolve_pronoun(user_id: str, message: str) -> tuple[str, str]:
    current_ai, current_user = load_pronoun(user_id)
    if current_ai == "mình" and current_user == "bạn":
        inferred = infer_pronoun(message)
        if inferred:
            save_pronoun(user_id, inferred[0], inferred[1])
            return inferred
    return current_ai, current_user


# ── Importance score ───────────────────────────────────────────────────────


def score_importance(text: str, emotion_intensity: int) -> int:
    score = 5
    lower = text.lower()

    high_signals = [
        "hãy nhớ", "remember this", "gọi mình là", "tên mình là",
        "my name is", "mục tiêu của mình", "mình luôn", "mình rất sợ",
        "đừng", "không thích bị", "boundary",
    ]
    medium_signals = [
        "công việc", "gia đình", "dự án", "thất nghiệp", "người yêu",
        "stress", "áp lực", "career", "family", "relationship",
    ]

    if any(s in lower for s in high_signals):
        score += 3
    elif any(s in lower for s in medium_signals):
        score += 1

    if emotion_intensity >= 7:
        score += 2
    elif emotion_intensity >= 5:
        score += 1

    if len(text) > 150:
        score += 1

    return max(1, min(10, score))
