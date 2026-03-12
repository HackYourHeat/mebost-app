# --------------------------------------------------
# Prompt Arbiter — MEBOST Hải Đăng V2.1
# --------------------------------------------------
# Khi nhiều engine cùng nói về "độ sâu" hoặc "cách nói",
# arbiter quyết định ai thắng — trước khi inject vào prompt.
#
# Nguyên tắc ưu tiên (từ cao xuống thấp):
#   1. Safety (trust thấp → block deep)
#   2. Temporal (first_time / return → override depth)
#   3. Policy (chế độ listen_only → im echo + gravity)
#   4. Trust + Momentum cùng cao → cho phép deep
#   5. Gravity + Echo → chỉ inject khi không xung đột với trên
#   6. Tone/personality hints → chỉ inject phần không trùng
# --------------------------------------------------

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ArbiterContext:
    trust:              float = 0.30
    momentum:           float = 0.00
    gravity:            float = 0.00
    echo_strength:      float = 0.00
    emotion_intensity:  int   = 0
    policy_mode:        str   = "normal_companion"
    session_continuity: str   = "continuous"   # first_time|continuous|pause|return
    distress:           float = 0.00
    pressure:           float = 0.00
    companion_posture:  str   = ""       # từ relational_continuity_engine


@dataclass
class ArbiterDecision:
    # Độ sâu cho phép lượt này
    depth_allowed:       str   = "pending" # pending → resolved by rule 5
    # Có inject echo không
    inject_echo:         bool  = True
    # Có inject gravity hook không
    inject_gravity_hook: bool  = True
    # Có inject momentum hint không
    inject_momentum:     bool  = True
    # Có inject trust hint không
    inject_trust:        bool  = True
    # Label chung để LLM hiểu ưu tiên
    override_note:       str   = ""
    # Danh sách lý do (debug)
    reasons:             list[str] = field(default_factory=list)


# --------------------------------------------------
# Bảng ưu tiên
# --------------------------------------------------

def arbitrate(ctx: ArbiterContext) -> ArbiterDecision:
    """
    Nhận context từ tất cả engines → trả ra ArbiterDecision
    nói rõ: ai được phép inject, độ sâu nào được phép.
    """
    d       = ArbiterDecision()
    reasons = d.reasons

    # ── 1. SAFETY: trust thấp → block deep tuyệt đối ──────────
    if ctx.trust < 0.35:
        d.depth_allowed       = "light"
        d.inject_echo         = ctx.echo_strength <= 0.55   # chỉ echo nhẹ
        d.inject_gravity_hook = False
        d.inject_momentum     = False
        d.inject_trust        = True
        d.override_note       = (
            "Trust còn thấp — giữ thật nhẹ nhàng. "
            "Không đặt câu hỏi về cảm xúc sâu. Chỉ lắng nghe."
        )
        reasons.append("trust<0.35 → light only")
        return d

    # ── 2. TEMPORAL: first_time / return ──────────────────────
    if ctx.session_continuity == "first_time":
        d.depth_allowed       = "light"
        d.inject_echo         = False   # không echo ngay lần đầu
        d.inject_gravity_hook = False
        d.inject_momentum     = False
        d.override_note       = (
            "Lần đầu gặp — chào đón tự nhiên, không đi vào chiều sâu cảm xúc ngay."
        )
        reasons.append("first_time → light, no echo")
        return d

    if ctx.session_continuity == "return" and ctx.trust < 0.50:
        d.depth_allowed       = "light"
        d.inject_gravity_hook = False
        d.override_note       = (
            "User vừa quay lại sau khoảng nghỉ — kết nối lại trước, "
            "chưa vội đi vào chiều sâu."
        )
        reasons.append("return + trust<0.50 → reconnect first")

    # ── 3. POLICY OVERRIDES ───────────────────────────────────
    if ctx.policy_mode == "listen_only":
        d.inject_echo         = False
        d.inject_gravity_hook = False
        d.inject_momentum     = False
        d.depth_allowed       = "light"
        d.override_note       = (
            "Chế độ lắng nghe — không hỏi thêm, không echo nặng. "
            "Chỉ hiện diện."
        )
        reasons.append("policy=listen_only → silence mode")
        return d

    if ctx.policy_mode == "reflect_first":
        d.inject_gravity_hook = False   # reflect trước, không kéo tiếp
        reasons.append("policy=reflect_first → no gravity hook")

    # ── 4. HIGH DISTRESS GUARD ───────────────────────────────
    # Khi user đang distress cao → không kéo vào sâu hơn
    if ctx.distress >= 0.70 or ctx.pressure >= 0.75:
        d.depth_allowed       = "medium" if d.depth_allowed != "light" else "light"
        d.inject_gravity_hook = False
        d.override_note       = (
            (d.override_note + " ") if d.override_note else ""
        ) + "Distress cao — ưu tiên ổn định, không khai thác thêm."
        reasons.append(f"distress={ctx.distress:.2f}/pressure={ctx.pressure:.2f} → no deepen")

    # ── 5. DEPTH RESOLUTION ──────────────────────────────────
    # Trust + Momentum cùng cao → deep được phép
    if True:  # always resolve depth
        if ctx.trust >= 0.60 and ctx.momentum >= 0.60:
            d.depth_allowed = "deep"
            reasons.append("trust≥0.60 + momentum≥0.60 → deep")
        elif ctx.trust >= 0.45 or ctx.momentum >= 0.45:
            d.depth_allowed = "medium"
            reasons.append("trust/momentum moderate → medium")
        else:
            d.depth_allowed = "light"
            reasons.append("trust+momentum both low → light")

    # ── 6. ECHO / GRAVITY CONFLICT RESOLUTION ────────────────
    # Nếu echo nặng + gravity hook cùng tồn tại → chỉ giữ echo
    # (tránh double-pull: vừa reflect sâu vừa kéo tiếp)
    if (d.inject_echo and ctx.echo_strength >= 0.70
            and d.inject_gravity_hook and ctx.gravity >= 0.55):
        d.inject_gravity_hook = False
        reasons.append("echo_strong + gravity → drop gravity hook (avoid double-pull)")

    # ── 7. DEPTH → INJECT FLAGS ──────────────────────────────
    if d.depth_allowed in ("light", "pending"):
        d.depth_allowed       = "light"
        d.inject_echo         = d.inject_echo and ctx.echo_strength <= 0.60
        d.inject_gravity_hook = False
        d.inject_momentum     = False

    # ── 8. CONTINUITY POSTURE INTEGRATION ──────────────
    # builder_companion: nếu an toàn, cho phép medium minimum (không ép light)
    if ctx.companion_posture == "builder_companion":
        if d.depth_allowed == "light" and ctx.trust >= 0.40:
            # builder cần ít nhất medium để đồng hành — nhưng safety rule 1 không bao giờ bị override
            if ctx.trust >= 0.35:   # trust đã pass rule 1
                d.depth_allowed = "medium"
                reasons.append("builder_companion + trust≥0.40 → promote to medium")

    return d


# --------------------------------------------------
# Depth → single override note cho prompt
# --------------------------------------------------

_DEPTH_NOTES: dict[str, str] = {
    "light":  (
        "Lượt này: giữ nhẹ nhàng. "
        "Phản chiếu đơn giản, không đặt câu hỏi sâu."
    ),
    "medium": (
        "Lượt này: có thể phản chiếu vừa phải và đặt một câu hỏi mở nhẹ."
    ),
    "deep":   (
        "Lượt này: không gian đủ an toàn — "
        "có thể đi vào chiều sâu, phản chiếu thật sự, "
        "và đặt câu hỏi chạm vào điều đang thật sự xảy ra."
    ),
}


def depth_note(decision: ArbiterDecision) -> str:
    return _DEPTH_NOTES.get(decision.depth_allowed, "")
