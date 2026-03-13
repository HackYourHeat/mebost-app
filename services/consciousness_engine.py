# --------------------------------------------------
# Consciousness Engine — MEBOST Hải Đăng V1.1
# 7-layer cognitive architecture.
# Không phải AI có ý thức —
# đây là cognitive architecture giúp AI:
# perceive → feel → remember → reflect → choose
# --------------------------------------------------

from __future__ import annotations

import re

# --------------------------------------------------
# Layer 1 — Perception
# --------------------------------------------------

_COMPLEX_PATTERNS = [
    r"\bmà\b", r"\bnhưng\b", r"\btuy nhiên\b", r"\bdù\b", r"\bmặc dù\b",
    r"\bbut\b", r"\bhowever\b", r"\balthough\b", r"\byet\b", r"\beven though\b",
]

_NEGATIVE_TONE = [
    "không", "chẳng", "chưa", "mất", "buồn", "lo", "sợ", "tức",
    "no", "not", "never", "lost", "sad", "fear", "angry",
]

_POSITIVE_TONE = [
    "vui", "tốt", "ổn", "tuyệt", "hạnh phúc", "yêu", "hope",
    "happy", "great", "love", "good", "okay", "fine",
]


def perceive_message(message: str) -> dict:
    """
    Layer 1 — Tiếp nhận message, phân tích tín hiệu cơ bản.

    Returns:
        {
          "message_length": int,
          "complexity":     float,   # 0.0 – 1.0
          "tone_hint":      str      # "positive" | "negative" | "mixed" | "neutral"
        }
    """
    stripped = message.strip()
    length   = len(stripped)

    # Complexity: câu dài + nhiều mệnh đề phức
    clause_count  = len(re.findall(r"[,;.!?…]", stripped)) + 1
    complex_hits  = sum(1 for p in _COMPLEX_PATTERNS if re.search(p, stripped, re.I))
    raw_complexity = min(1.0, (length / 300) * 0.5 + (clause_count / 10) * 0.3 + (complex_hits / 5) * 0.2)

    # Tone
    low         = stripped.lower()
    pos_count   = sum(1 for w in _POSITIVE_TONE if w in low)
    neg_count   = sum(1 for w in _NEGATIVE_TONE if w in low)

    if pos_count > 0 and neg_count > 0:
        tone = "mixed"
    elif neg_count > pos_count:
        tone = "negative"
    elif pos_count > neg_count:
        tone = "positive"
    else:
        tone = "neutral"

    return {
        "message_length": length,
        "complexity":     round(raw_complexity, 3),
        "tone_hint":      tone,
    }


# --------------------------------------------------
# Layer 5 — Reflection
# --------------------------------------------------

def build_reflection_state(
    emotion_intensity: int,
    intent: str,
    complexity: float,
) -> dict:
    """
    Layer 5 — Tạo reflection vector.
    AI không trả lời ngay mà đánh giá mức độ cần phản chiếu.

    Rules:
      emotion_intensity > 6  → cần reflect
      intent == "vent"       → cần reflect
      complexity > 0.5       → reflect sâu hơn

    Returns:
        {
          "reflection_depth": float,   # 0.0 – 1.0
          "needs_reflection": bool
        }
    """
    depth = 0.0

    if emotion_intensity > 6:
        depth += (emotion_intensity - 6) / 4 * 0.5    # max +0.5

    if intent == "vent":
        depth += 0.3

    if complexity > 0.5:
        depth += (complexity - 0.5) * 0.4             # max +0.2

    depth = round(min(1.0, depth), 3)
    needs_reflection = (emotion_intensity > 6) or (intent == "vent")

    return {
        "reflection_depth": depth,
        "needs_reflection": needs_reflection,
    }


# --------------------------------------------------
# Layer 6 — Policy
# --------------------------------------------------

def select_response_policy(
    emotion: str,
    intensity: int,
    intent: str,
    reflection_depth: float,
) -> dict:
    """
    Layer 6 — Chọn response mode dựa trên consciousness state.

    Priority order:
      1. Heavy emotion + high reflection → reflect_first
      2. Vent intent                     → listen_only
      3. High reflection depth           → deep_reflection
      4. Help intent, light emotion      → supportive_help
      5. Default                         → normal_companion

    Returns:
        {"policy": str, "advice_allowed": bool}
    """
    # ── Rule 1: intent=help LUÔN được phép advice ─────────────
    # Kể cả khi emotion nặng — user xin giúp trực tiếp thì phải giúp.
    # Style vẫn gentle, nhưng không block advice.
    if intent == "help":
        return {"policy": "supportive_help", "advice_allowed": True}

    # ── Rule 2: vent → chỉ nghe, không khuyên ─────────────────
    if intent == "vent":
        return {"policy": "listen_only", "advice_allowed": False}

    # ── Rule 3: cảm xúc nặng, chưa xin giúp → reflect trước ──
    if emotion in ("sad", "anxious", "angry") and intensity >= 7:
        return {"policy": "reflect_first", "advice_allowed": False}

    # ── Rule 4: reflection sâu → deep mode ────────────────────
    if reflection_depth >= 0.6:
        return {"policy": "deep_reflection", "advice_allowed": False}

    return {"policy": "normal_companion", "advice_allowed": False}


# --------------------------------------------------
# Layer 4 — Memory relevance
# --------------------------------------------------

def assess_memory_relevance(memory_summary: str, message: str) -> float:
    """
    Layer 4 — Đánh giá mức độ liên quan của ký ức với tin nhắn hiện tại.

    Simple keyword overlap; không cần LLM.

    Returns:
        relevance (float, 0.0 – 1.0)
    """
    if not memory_summary or not memory_summary.strip():
        return 0.0

    msg_words  = set(re.findall(r"\w+", message.lower()))
    mem_words  = set(re.findall(r"\w+", memory_summary.lower()))
    stop_words = {
        "và", "của", "là", "có", "không", "một", "the", "a", "an",
        "is", "are", "was", "were", "in", "on", "at", "to", "for",
    }
    msg_words -= stop_words
    mem_words -= stop_words

    if not msg_words:
        return 0.0

    overlap = len(msg_words & mem_words) / len(msg_words)
    return round(min(1.0, overlap), 3)


# --------------------------------------------------
# Main API — build_consciousness_state
# --------------------------------------------------

def build_consciousness_state(
    message: str,
    emotion_ctx: dict,
    intent_ctx: dict,
    memory_summary: str,
) -> dict:
    """
    Chạy toàn bộ 7-layer consciousness pipeline.

    Args:
        message       : tin nhắn người dùng
        emotion_ctx   : output từ build_emotion_context()
        intent_ctx    : output từ build_intent_context()
        memory_summary: output từ get_active_memory_summary()

    Returns:
        {
          "perception": {...},
          "emotion":    {...},
          "intent":     {...},
          "memory":     {...},
          "reflection": {...},
          "policy":     {...},
        }
    """
    # L1 — Perception
    perception = perceive_message(message)

    # L2 — Emotion (đã tính ngoài, wrap lại)
    emotion = {
        "emotion":   emotion_ctx.get("emotion", "neutral"),
        "intensity": emotion_ctx.get("intensity", 5),
    }

    # L3 — Intent (đã tính ngoài, wrap lại)
    intent = {
        "intent": intent_ctx.get("intent", "talk"),
    }

    # L4 — Memory
    relevance = assess_memory_relevance(memory_summary, message)
    memory    = {
        "memory_summary":   memory_summary or "",
        "memory_relevance": relevance,
    }

    # L5 — Reflection
    reflection = build_reflection_state(
        emotion["intensity"],
        intent["intent"],
        perception["complexity"],
    )

    # L6 — Policy
    policy = select_response_policy(
        emotion["emotion"],
        emotion["intensity"],
        intent["intent"],
        reflection["reflection_depth"],
    )

    # L7 — Response layer handled by prompt_builder + llm_adapter in app.py

    return {
        "perception": perception,
        "emotion":    emotion,
        "intent":     intent,
        "memory":     memory,
        "reflection": reflection,
        "policy":     policy,
    }


def consciousness_to_policy_dict(conscious_state: dict) -> dict:
    """
    Chuyển consciousness policy sang format mà response_policy / prompt_builder hiểu.
    """
    p = conscious_state.get("policy", {})
    mode_map = {
        "reflect_first":   "reflect_first",
        "listen_only":     "listen_only",
        "deep_reflection": "deep_reflection",
        "supportive_help": "supportive_help",
        "normal_companion":"normal_companion",
    }
    policy_name = p.get("policy", "normal_companion")
    return {
        "mode":           mode_map.get(policy_name, "normal_companion"),
        "reply_style":    _reply_style(policy_name),
        "advice_allowed": p.get("advice_allowed", False),
    }


def _reply_style(policy: str) -> str:
    return {
        "reflect_first":   "gentle_short",
        "listen_only":     "soft_reflective",
        "deep_reflection": "slow_reflective",
        "supportive_help": "gentle_guidance",
        "normal_companion":"warm_balanced",
    }.get(policy, "warm_balanced")


# --------------------------------------------------
# Example / self-test
# --------------------------------------------------

def test_consciousness_layer() -> None:
    """
    Chạy thử 3 kịch bản để kiểm tra 7-layer pipeline.
    """
    cases = [
        {
            "label":    "Nhẹ nhàng",
            "message":  "Hôm nay ổn.",
            "emotion":  {"emotion": "neutral", "intensity": 3},
            "intent":   {"intent": "talk"},
            "memory":   "",
        },
        {
            "label":    "Lo lắng — cần reflect",
            "message":  "Mình đang rất lo về dự án tháng 10, không biết có kịp không.",
            "emotion":  {"emotion": "anxious", "intensity": 7},
            "intent":   {"intent": "vent"},
            "memory":   "Người dùng đang làm dự án quan trọng, có xu hướng lo lắng khi deadline gần.",
        },
        {
            "label":    "Nặng nề — cần phản chiếu sâu",
            "message":  "Thật ra mình cũng sợ thất bại lắm, cả nhóm đang nhìn vào mình nhưng mình không biết mình có đủ sức không.",
            "emotion":  {"emotion": "anxious", "intensity": 9},
            "intent":   {"intent": "reflection"},
            "memory":   "Người dùng thường đặt kỳ vọng cao vào bản thân.",
        },
    ]

    print("─── Consciousness Layer — 7 Tầng Nhận Thức ───")
    for c in cases:
        cs = build_consciousness_state(c["message"], c["emotion"], c["intent"], c["memory"])
        p  = cs["perception"]
        r  = cs["reflection"]
        pl = cs["policy"]
        print(f"\n[{c['label']}]")
        print(f"  Perception : len={p['message_length']} complexity={p['complexity']:.2f} tone={p['tone_hint']}")
        print(f"  Reflection : depth={r['reflection_depth']:.2f} needs={r['needs_reflection']}")
        print(f"  Policy     : {pl['policy']} (advice={pl['advice_allowed']})")
        print(f"  Mem relevance: {cs['memory']['memory_relevance']:.2f}")
    print("\n──────────────────────────────────────────────")


if __name__ == "__main__":
    test_consciousness_layer()
