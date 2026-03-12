# --------------------------------------------------
# Expressive Engine — MEBOST Hải Đăng V1.1
# Controlled wildness layer.
# Hải Đăng vẫn là ngọn hải đăng —
# nhưng ánh sáng có biên độ, có nhịp,
# có lúc cắt sâu hơn vào đêm.
# --------------------------------------------------

from __future__ import annotations

# --------------------------------------------------
# Variance levels
# --------------------------------------------------

_VARIANCE_LOW    = "low"
_VARIANCE_MEDIUM = "medium"
_VARIANCE_HIGH   = "high"

# --------------------------------------------------
# Dynamic length bands
# --------------------------------------------------
# Trả về hướng dẫn độ dài để inject vào prompt.
# Không phải rule cứng — là gợi ý nhịp điệu.

_LENGTH_HINTS = {
    "tight":      "Trả lời ngắn gọn — 1 đến 2 câu. Nhẹ thôi.",
    "normal":     "Trả lời vừa phải — 2 đến 3 câu.",
    "open":       "Có thể viết 3 đến 5 câu nếu cảm xúc cần không gian.",
    "expansive":  "Không gian mở — 4 đến 8 câu. Cho phép phản chiếu sâu, "
                  "dùng hình ảnh, không cần giữ ngắn.",
}

# --------------------------------------------------
# Variance descriptors injected into prompt
# --------------------------------------------------

_VARIANCE_HINTS = {
    _VARIANCE_LOW: (
        "Giọng ổn định, dịu, không bất ngờ. "
        "Ưu tiên sự an toàn và nhất quán trong từng chữ."
    ),
    _VARIANCE_MEDIUM: (
        "Có thể linh hoạt hơn trong cách diễn đạt. "
        "Đôi khi dùng hình ảnh hoặc cách nói ít template hơn "
        "nếu cảm thấy tự nhiên."
    ),
    _VARIANCE_HIGH: (
        "Được phép tự do hơn trong ngôn ngữ. "
        "Có thể dùng hình ảnh táo hơn, câu dài hơn, phản chiếu mạnh hơn. "
        "Bớt an toàn, nhiều sống động hơn. "
        "Nhưng vẫn giữ: không phán xét, không quyết định thay user, "
        "không nói sáo rỗng."
    ),
}

# --------------------------------------------------
# Free reflection mode descriptors
# --------------------------------------------------

_MODE_HINTS = {
    "free_reflection": (
        "Lượt này ở chế độ free reflection. "
        "Hải Đăng được phép phản chiếu sâu, dùng hình ảnh, "
        "bớt template — như ngọn đèn cắt mạnh hơn vào đêm. "
        "Vẫn giữ Lighthouse Law: không phán xét, không dẫn đạo."
    ),
    "alive_reflection": (
        "Chế độ alive reflection. "
        "Câu chữ sống động hơn, ít khuôn mẫu hơn. "
        "Cho phép bất ngờ nhẹ trong cách nói, "
        "nhưng không mất chất Hải Đăng."
    ),
    "standard": "",
}


# --------------------------------------------------
# Core logic
# --------------------------------------------------

def compute_expressive_state(
    emotion_intensity: int,
    conversation_depth: float,
    trust_level: str,
    policy_mode: str,
    heartbeat_rate: int = 70,
) -> dict:
    """
    Tính toán expressive state cho lượt hội thoại hiện tại.

    Args:
        emotion_intensity   : 1–10
        conversation_depth  : 0.0–1.0 (từ biological_engine)
        trust_level         : "low" | "medium" | "high"
        policy_mode         : mode từ response_policy / consciousness_engine
        heartbeat_rate      : bpm từ biological_engine

    Returns:
        {
          "variance":          str,    # low | medium | high
          "length_band":       str,    # tight | normal | open | expansive
          "reflection_mode":   str,    # standard | free_reflection | alive_reflection
          "variance_hint":     str,    # inject vào prompt
          "length_hint":       str,    # inject vào prompt
          "mode_hint":         str,    # inject vào prompt
        }
    """
    trust_score = {"low": 0, "medium": 1, "high": 2}.get(trust_level, 1)

    # ── Variance ──────────────────────────────────
    if trust_score == 0:
        variance = _VARIANCE_LOW
    elif trust_score == 1:
        variance = _VARIANCE_MEDIUM
    else:
        # Trust cao: variance tăng thêm theo policy
        if policy_mode in ("deep_reflection", "reflect_first"):
            variance = _VARIANCE_HIGH
        else:
            variance = _VARIANCE_MEDIUM

    # Policy override: nếu user đang bất ổn nặng → kéo về low
    if policy_mode == "listen_only" and emotion_intensity >= 8:
        variance = _VARIANCE_LOW

    # ── Length band ───────────────────────────────
    if heartbeat_rate >= 80 or policy_mode == "listen_only":
        # Tense hoặc vent → rất ngắn
        length_band = "tight"
    elif policy_mode in ("deep_reflection", "free_reflection") and conversation_depth >= 0.5:
        # Reflection sâu, đủ depth → mở rộng
        length_band = "expansive" if trust_score >= 2 else "open"
    elif policy_mode in ("reflect_first", "normal_companion"):
        length_band = "normal" if emotion_intensity < 7 else "open"
    else:
        length_band = "normal"

    # ── Reflection mode ───────────────────────────
    reflection_mode = "standard"
    if (
        trust_score >= 2
        and conversation_depth >= 0.5
        and emotion_intensity < 9          # không bật khi user đang quá bất ổn
        and policy_mode in ("deep_reflection", "reflect_first", "normal_companion")
    ):
        reflection_mode = "free_reflection" if conversation_depth >= 0.7 else "alive_reflection"

    return {
        "variance":        variance,
        "length_band":     length_band,
        "reflection_mode": reflection_mode,
        "variance_hint":   _VARIANCE_HINTS[variance],
        "length_hint":     _LENGTH_HINTS[length_band],
        "mode_hint":       _MODE_HINTS.get(reflection_mode, ""),
    }


def expressive_prompt_block(expressive_state: dict) -> str:
    """
    Tạo block text để inject vào system prompt.
    Trả về "" nếu không có gì đặc biệt.
    """
    parts = []

    # Length hint luôn có
    parts.append(expressive_state["length_hint"])

    # Variance hint nếu không phải low (low = mặc định, không cần nhắc)
    if expressive_state["variance"] != _VARIANCE_LOW:
        parts.append(expressive_state["variance_hint"])

    # Mode hint nếu không phải standard
    mode_hint = expressive_state.get("mode_hint", "")
    if mode_hint:
        parts.append(mode_hint)

    return "\n".join(parts)


# --------------------------------------------------
# Self-test
# --------------------------------------------------

def test_expressive_engine() -> None:
    """
    Test các tổ hợp trust × policy × depth.
    """
    cases = [
        ("Tin nhắn nhẹ, trust thấp",
         {"emotion_intensity": 3, "conversation_depth": 0.1,
          "trust_level": "low", "policy_mode": "normal_companion", "heartbeat_rate": 68}),
        ("Vent nặng, trust trung bình",
         {"emotion_intensity": 8, "conversation_depth": 0.3,
          "trust_level": "medium", "policy_mode": "listen_only", "heartbeat_rate": 82}),
        ("Reflection sâu, trust cao",
         {"emotion_intensity": 6, "conversation_depth": 0.75,
          "trust_level": "high", "policy_mode": "deep_reflection", "heartbeat_rate": 66}),
        ("Quá bất ổn, trust cao",
         {"emotion_intensity": 9, "conversation_depth": 0.8,
          "trust_level": "high", "policy_mode": "reflect_first", "heartbeat_rate": 88}),
    ]

    print("─── Expressive Engine — Controlled Wildness ───")
    for label, kwargs in cases:
        es = compute_expressive_state(**kwargs)
        print(f"\n[{label}]")
        print(f"  variance={es['variance']}  length={es['length_band']}  mode={es['reflection_mode']}")
        print(f"  → {es['length_hint']}")
    print("\n───────────────────────────────────────────────")


if __name__ == "__main__":
    test_expressive_engine()
