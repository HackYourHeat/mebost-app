# --------------------------------------------------
# Presence Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Presence = cảm giác AI "đang ở đây" với user trong khoảnh khắc này.
#
# Không phải trust (an toàn dài hạn).
# Không phải familiarity (quen biết theo thời gian).
# Không phải gravity (kéo hội thoại tiếp).
#
# Presence điều tiết NHỊP và ĐỘ MỀM của phản hồi:
#   - khi nào nên chậm lại
#   - khi nào nên để khoảng lặng
#   - khi nào không hỏi tiếp
#   - khi nào "giữ chỗ" thay vì khai thác
#
# 4 modes:
#   quiet   — nhẹ nhàng, không đẩy, đồng hành từ xa
#   steady  — hiện diện bình thường, cân bằng
#   close   — ấm hơn, tự nhiên hơn (chỉ khi trust + familiarity đủ)
#   holding — user đang mong manh, AI "giữ chỗ", không explore
#
# Không tạo bảng mới. Stateless — tính từ context hiện có.
# Không gọi LLM. Fail-safe.
# --------------------------------------------------

from __future__ import annotations

# --------------------------------------------------
# Output schema
# --------------------------------------------------

def _default_presence() -> dict:
    return {
        "presence_mode":     "steady",
        "pace":              "normal",
        "silence_tolerance": 0.40,
        "question_pressure": 0.50,
        "softness_bias":     0.50,
        "presence_hint":     "",
    }


# --------------------------------------------------
# Public API
# --------------------------------------------------

def compute_presence(
    emotion_ctx:     dict | None = None,
    internal_state:  dict | None = None,
    bio_state:       dict | None = None,
    momentum:        float = 0.0,
    trust:           float = 0.30,
    gravity:         float = 0.0,
    policy:          dict | None = None,
    temporal_ctx:    dict | None = None,
    familiarity:     dict | None = None,
) -> dict:
    """
    Tính presence state từ toàn bộ context hiện có.
    Trả về dict an toàn — không bao giờ raise.
    """
    try:
        return _compute(
            emotion_ctx    or {},
            internal_state or {},
            bio_state      or {},
            momentum, trust, gravity,
            policy         or {},
            temporal_ctx   or {},
            familiarity    or {},
        )
    except Exception:
        return _default_presence()


def presence_prompt_block(presence: dict) -> str:
    """
    Chuyển presence state → hướng dẫn ngắn gọn cho LLM.
    Không lặp với trust/momentum/policy blocks đã có.
    """
    if not presence:
        return ""

    mode  = presence.get("presence_mode", "steady")
    pace  = presence.get("pace", "normal")
    qp    = presence.get("question_pressure", 0.50)
    soft  = presence.get("softness_bias", 0.50)
    hint  = presence.get("presence_hint", "")

    lines: list[str] = []

    # Mode
    _MODE_LINES = {
        "quiet":   "Lượt này: hiện diện nhẹ nhàng — không đẩy, không kéo. Chỉ ở đây.",
        "steady":  "Lượt này: đồng hành bình thường — cân bằng giữa lắng nghe và phản chiếu.",
        "close":   "Lượt này: ấm hơn và tự nhiên hơn — khoảng cách đã được rút ngắn.",
        "holding": "Lượt này: giữ chỗ — user cần được chứa đựng, không cần được dẫn dắt.",
    }
    mode_line = _MODE_LINES.get(mode, "")
    if mode_line:
        lines.append(mode_line)

    # Pace
    if pace == "slow":
        lines.append("Nhịp chậm — đừng vội điền đầy khoảng trống.")

    # Question pressure
    if qp <= 0.20:
        lines.append("Không đặt câu hỏi lượt này trừ khi thực sự tự nhiên.")
    elif qp <= 0.35:
        lines.append("Hạn chế hỏi — tối đa một câu hỏi nhẹ nếu cần.")

    # Softness
    if soft >= 0.75:
        lines.append("Giọng mềm hơn bình thường — như đặt tay nhẹ lên vai.")

    # Specific hint
    if hint:
        lines.append(hint)

    return "\n".join(lines) if lines else ""


# --------------------------------------------------
# Core logic
# --------------------------------------------------

def _compute(
    emotion_ctx:    dict,
    internal_state: dict,
    bio_state:      dict,
    momentum:       float,
    trust:          float,
    gravity:        float,
    policy:         dict,
    temporal_ctx:   dict,
    familiarity:    dict,
) -> dict:

    distress  = float(internal_state.get("distress",  0.0))
    pressure  = float(internal_state.get("pressure",  0.0))
    depth     = float(internal_state.get("depth",     0.0))
    intensity = int(emotion_ctx.get("intensity", 5))
    emotion   = str(emotion_ctx.get("emotion", "neutral")).lower()
    policy_mode    = str(policy.get("mode", "normal_companion"))
    continuity     = str(temporal_ctx.get("session_continuity", "continuous"))
    fam_level      = str(familiarity.get("familiarity_level", "new"))
    fam_relaxation = float(familiarity.get("tone_relaxation", 0.0))

    # ── Tính các tín hiệu thô ─────────────────────────────────

    # Fragility: kết hợp distress, pressure, emotion nặng
    _HEAVY = {"sad", "anxious", "overwhelmed", "scared", "grief",
              "desperate", "hopeless", "frustrated"}
    emotion_weight = 0.8 if emotion in _HEAVY else (0.3 if emotion == "tired" else 0.0)
    fragility = min(1.0, distress * 0.5 + pressure * 0.3 + emotion_weight * 0.2)

    # Openness: khi trust + familiarity đủ → cho phép close
    openness = min(1.0, trust * 0.6 + fam_relaxation * 0.4)

    # ── Rule-based mode selection ─────────────────────────────

    # Rule A: listen_only → holding
    if policy_mode == "listen_only":
        return _make(
            mode="holding", pace="slow",
            silence=0.80, q_pressure=0.10, softness=0.85,
            hint="Chế độ lắng nghe — không dẫn dắt, không hỏi. Chỉ hiện diện.",
        )

    # Rule B: user fragile / distress cao → holding
    if fragility >= 0.65 or (intensity >= 8 and emotion in _HEAVY):
        return _make(
            mode="holding", pace="slow",
            silence=0.75, q_pressure=0.15, softness=0.80,
            hint="User đang mong manh — giữ chỗ, không explore.",
        )

    # Rule C: first time → quiet (chưa đủ quen để gần)
    if continuity == "first_time" or trust < 0.30:
        return _make(
            mode="quiet", pace="normal",
            silence=0.50, q_pressure=0.30, softness=0.60,
            hint="",
        )

    # Rule D: trust + familiarity đủ + fragility thấp → close
    if openness >= 0.60 and fragility < 0.35 and fam_level in ("familiar", "trusted"):
        # Nhưng nếu gravity cao + fragility trung bình → đừng close
        if gravity >= 0.65 and fragility >= 0.25:
            pass  # fall through to steady
        else:
            return _make(
                mode="close", pace="normal",
                silence=0.30, q_pressure=0.55, softness=0.65,
                hint="",
            )

    # Rule E: momentum thấp → reduce question pressure
    if momentum <= 0.20:
        return _make(
            mode="quiet", pace="slow",
            silence=0.65, q_pressure=0.20, softness=0.60,
            hint="Đà hội thoại thấp — không kéo tiếp, để user tự dẫn.",
        )

    # Rule F: gravity cao nhưng user fragile → presence thắng gravity
    if gravity >= 0.60 and fragility >= 0.45:
        return _make(
            mode="holding", pace="slow",
            silence=0.70, q_pressure=0.20, softness=0.75,
            hint="Gravity cao nhưng user cần được giữ — ưu tiên hiện diện hơn kéo tiếp.",
        )

    # Default: steady
    # Tune theo các tín hiệu nhỏ
    q_pressure = 0.50
    softness   = 0.50
    silence    = 0.40

    if fragility >= 0.30:
        q_pressure -= 0.15
        softness   += 0.15
        silence    += 0.10

    if momentum >= 0.60:
        q_pressure += 0.10

    if depth >= 0.60:
        softness += 0.10
        silence  += 0.10

    return _make(
        mode="steady", pace="normal",
        silence=_clamp(silence),
        q_pressure=_clamp(q_pressure),
        softness=_clamp(softness),
        hint="",
    )


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _make(
    mode: str, pace: str,
    silence: float, q_pressure: float, softness: float,
    hint: str,
) -> dict:
    return {
        "presence_mode":     mode,
        "pace":              pace,
        "silence_tolerance": round(silence,    3),
        "question_pressure": round(q_pressure, 3),
        "softness_bias":     round(softness,   3),
        "presence_hint":     hint,
    }


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return round(max(lo, min(hi, v)), 3)
