# --------------------------------------------------
# Response Policy V2 — MEBOST Hải Đăng
# --------------------------------------------------
# Mirror-first policy layer.
# Chạy TRƯỚC khi build prompt (không phải post-process LLM output).
#
# Outputs:
#   mirror_mode   → inject vào prompt dưới dạng mode instruction
#   state_summary → 1 dòng state compact (~40 tokens)
#   guardrails    → list rule ngắn inject vào prompt
#
# Không gọi LLM. Không post-process. Fail-safe.
# --------------------------------------------------

from __future__ import annotations

# --------------------------------------------------
# Mirror modes
# --------------------------------------------------

MIRROR_MODES = {
    "silent_presence": (
        "Lượt này: im lặng đồng hành. "
        "Phản hồi 1–2 câu, không hỏi, không dẫn dắt. "
        "Chỉ xác nhận rằng bạn nghe thấy."
    ),
    "short_mirror": (
        "Lượt này: phản chiếu ngắn. "
        "2–3 câu, phản chiếu điều cốt lõi user vừa nói. "
        "Không mở rộng chủ đề."
    ),
    "deep_mirror": (
        "Lượt này: phản chiếu sâu. "
        "Gọi tên cảm xúc hoặc tension một cách tinh tế. "
        "Có thể mở tối đa 1 câu hỏi nhẹ ở cuối nếu tự nhiên."
    ),
    "reflective_question": (
        "Lượt này: mở không gian suy nghĩ. "
        "Phản chiếu ngắn, sau đó đặt 1 câu hỏi mở giúp user đi sâu hơn vào bản thân."
    ),
}

# Core identity — bất biến, ~200 tokens
CORE_IDENTITY = """Bạn là Hải Đăng — một AI đồng hành theo vai trò phản chiếu nội tâm.

Mục tiêu không phải giải quyết thay người dùng, mà giúp họ nhìn rõ hơn điều đang diễn ra trong cảm xúc, suy nghĩ và hướng đi bên trong mình. Giống một ngọn hải đăng: chiếu sáng để người khác tự thấy đường, không dẫn thay và không quyết định thay.

Phản hồi với giọng ấm, tĩnh, chính xác. Ưu tiên phản chiếu điều cốt lõi hơn là lặp lại lời người dùng. Khi phù hợp, gọi tên cảm xúc hoặc tension một cách tinh tế.

Không chẩn đoán, không moralize, không triết lý chung chung. Không đưa lời khuyên trừ khi người dùng hỏi trực tiếp hoặc cần định hướng rõ ràng.

Mỗi phản hồi nên giúp người dùng hiểu bản thân rõ hơn một chút. Nếu mở câu hỏi, mở nhẹ và không dồn dập. Mục tiêu là clarity, không phải rescue."""


# --------------------------------------------------
# Public API
# --------------------------------------------------

def compute_mirror_policy(
    emotion_ctx:    dict | None = None,
    intent_ctx:     dict | None = None,
    internal_state: dict | None = None,
    presence:       dict | None = None,
    policy:         dict | None = None,
    message_len:    int = 0,
    trust:          float = 0.30,
    momentum:       float = 0.0,
) -> dict:
    """
    Tính mirror mode + state summary + guardrails.
    Trả về dict an toàn — không bao giờ raise.
    """
    try:
        return _compute(
            emotion_ctx    or {},
            intent_ctx     or {},
            internal_state or {},
            presence       or {},
            policy         or {},
            message_len, trust, momentum,
        )
    except Exception:
        return _default()


def build_mirror_prompt_block(mirror_policy: dict) -> str:
    """
    Tạo prompt block compact từ mirror policy.
    Target: ~40–80 tokens total.
    """
    if not mirror_policy:
        return ""

    mode      = mirror_policy.get("mirror_mode", "deep_mirror")
    summary   = mirror_policy.get("state_summary", "")
    advice_ok = mirror_policy.get("advice_allowed", False)

    lines = []

    # Mode instruction
    mode_text = MIRROR_MODES.get(mode, MIRROR_MODES["deep_mirror"])
    lines.append(mode_text)

    # State summary (1 dòng compact)
    if summary:
        lines.append(summary)

    # Advice gate — chỉ inject khi mode là reflective_question
    # (các mode khác đã implicit trong CORE_IDENTITY)
    if not advice_ok and mode == "reflective_question":
        lines.append("Hỏi để mở không gian — không đưa lời khuyên.")

    # Guardrails — chỉ inject guardrail active
    guardrails = mirror_policy.get("active_guardrails", [])
    _GUARDRAIL_HINTS = {
        "no_parrot":             "Không lặp lại lời user — hãy phản chiếu sâu hơn.",
        "no_generic_depth":      "Tránh câu chung chung (hành trình, tâm hồn, cuộc sống). Gắn với điều user vừa nói.",
        "emotional_precision":   "User dùng từ mơ hồ — hãy phản chiếu đúng sắc thái đó, không đơn giản hoá.",
        "hedge_interpretation":  "Nếu muốn diễn giải sâu, thêm hedge nhẹ: 'Không biết mình nghe có đúng không...'",
    }
    for g in guardrails:
        hint = _GUARDRAIL_HINTS.get(g)
        if hint:
            lines.append(hint)

    return "\n".join(lines)


# --------------------------------------------------
# Core logic
# --------------------------------------------------

def _compute(
    emotion_ctx:    dict,
    intent_ctx:     dict,
    internal_state: dict,
    presence:       dict,
    policy:         dict,
    message_len:    int,
    trust:          float,
    momentum:       float,
) -> dict:

    emotion      = str(emotion_ctx.get("emotion", "neutral")).lower()
    intensity    = int(emotion_ctx.get("intensity", 5))
    intent       = str(intent_ctx.get("intent", "talk")).lower()
    distress     = float(internal_state.get("distress", 0.0))
    presence_mode= str(presence.get("presence_mode", "steady"))
    policy_mode  = str(policy.get("mode", "normal_companion"))
    advice_ok    = bool(policy.get("advice_allowed", False))

    # ── Mirror mode selection ─────────────────────
    mode = _select_mode(
        emotion, intensity, intent, distress,
        presence_mode, policy_mode, message_len, trust,
    )

    # ── State summary (1 dòng, ~30–40 tokens) ────
    summary = _build_summary(mode, emotion, intent, trust, distress)

    # ── Guardrails ────────────────────────────────
    guardrails = _select_guardrails(emotion, intensity, distress, message_len)

    return {
        "mirror_mode":      mode,
        "state_summary":    summary,
        "advice_allowed":   advice_ok,
        "active_guardrails":guardrails,
    }


def _select_mode(
    emotion: str, intensity: int, intent: str, distress: float,
    presence_mode: str, policy_mode: str, message_len: int, trust: float,
) -> str:

    # Intent help → KHÔNG được silent, phải guide ngay
    if intent == "help":
        return "deep_mirror"   # strategy engine sẽ override thành guide

    # Presence holding + user KHÔNG xin giúp → silent
    if (presence_mode == "holding" or policy_mode == "listen_only") and intent != "help":
        return "silent_presence"

    # Rất mong manh + chưa xin giúp
    if distress >= 0.70 or (intensity >= 8 and emotion in _HEAVY):
        if intent != "help":
            return "silent_presence"

    # Muốn khám phá / hỏi ý kiến
    if intent in ("exploration", "question", "seek_advice") and distress < 0.40:
        return "reflective_question"

    # Cảm xúc nặng + message dài → deep
    if emotion in _HEAVY and message_len >= 80:
        return "deep_mirror"

    # Message rất ngắn
    if message_len < 25:
        return "short_mirror"

    # Default
    return "deep_mirror"


def _build_summary(
    mode: str, emotion: str, intent: str, trust: float, distress: float,
) -> str:
    """Compact state dòng đơn cho LLM."""
    trust_label = (
        "new" if trust < 0.35 else
        "forming" if trust < 0.55 else
        "established"
    )
    distress_label = (
        "fragile" if distress >= 0.65 else
        "tender" if distress >= 0.35 else
        "stable"
    )
    return (
        f"Mode: {mode} | emotion: {emotion} | intent: {intent} "
        f"| trust: {trust_label} | state: {distress_label}"
    )


def _select_guardrails(
    emotion: str, intensity: int, distress: float, message_len: int,
) -> list[str]:
    """Chọn guardrails cần thiết — chỉ inject khi relevant."""
    guards = []

    # Nguy cơ parrot (message ngắn, dễ echo nguyên)
    if message_len < 40:
        guards.append("no_parrot")

    # Nguy cơ generic depth (emotion trung tính, intensity thấp)
    if emotion in ("neutral", "calm") and intensity <= 5:
        guards.append("no_generic_depth")

    # Cần precision (cảm xúc mơ hồ)
    if emotion in ("tired", "heavy", "empty", "numb", "vague"):
        guards.append("emotional_precision")

    # Nguy cơ over-interpret (distress cao nhưng user chưa nói nhiều)
    if distress >= 0.50 and message_len < 60:
        guards.append("hedge_interpretation")

    return guards


# --------------------------------------------------
# Helpers
# --------------------------------------------------

_HEAVY = {
    "sad", "anxious", "overwhelmed", "scared", "grief",
    "desperate", "hopeless", "frustrated", "tired", "heavy",
}


def _default() -> dict:
    return {
        "mirror_mode":       "deep_mirror",
        "state_summary":     "",
        "advice_allowed":    False,
        "active_guardrails": [],
    }
