# --------------------------------------------------
# Prompt Builder — MEBOST Hải Đăng V3.2
# Mirror-first architecture.
#
# System prompt target: ~250–350 tokens (down from ~900)
# Structure:
#   [1] CORE_IDENTITY   — ~200t, bất biến
#   [2] Language rule   — ~10t
#   [3] Mirror mode     — ~40t, per-turn
#   [4] Pronoun         — ~10t
#   [5] Memory          — ~60t max
#   [6] Open loops      — ~20t max (nếu có)
# --------------------------------------------------

from __future__ import annotations

MAX_INPUT_CHARS = 5000

from services.response_policy_v2 import (
    CORE_IDENTITY,
    build_mirror_prompt_block,
)


# --------------------------------------------------
# Public API — signature giữ nguyên để không phá app.py
# --------------------------------------------------

def build_system_prompt(
    language:          str,
    display_name:      str,
    memory_summary:    str,
    policy:            dict,
    bio_state:         dict,
    conscious_state:   dict,
    life_graph_summary:dict,
    expressive_state:  dict,
    message_len:       int   = 0,
    listening_style:   str   = "gentle_companion",
    tone_profile:      dict | None = None,
    user_state:        dict | None = None,
    personality:       dict | None = None,
    conversation_turn: int   = 1,
    momentum:          float = 0.0,
    trust:             float = 0.30,
    temporal_ctx:      dict | None = None,
    gravity:           float = 0.0,
    gravity_hook:      str   = "",
    echo_text:         str   = "",
    echo_strength:     float = 0.0,
    distress:          float = 0.0,
    pressure:          float = 0.0,
    thread_context:    str   = "",
    pronoun_profile:   dict | None = None,
    relational_ctx:    dict | None = None,
    personality_dna:   dict | None = None,
    familiarity:       dict | None = None,
    presence:          dict | None = None,
    # Mirror policy — passed từ app.py nếu có, tính lại nếu không
    mirror_policy:     dict | None = None,
    emotion_ctx:       dict | None = None,
    intent_ctx:        dict | None = None,
) -> str:

    parts: list[str] = []

    # ── [1] Core identity ─────────────────────────
    parts.append(CORE_IDENTITY)

    # ── [2] Language ──────────────────────────────
    if language and language.lower() not in ("tiếng việt", "vietnamese", "vi"):
        parts.append(f"Respond in: {language}")

    # ── [3] Mirror mode block ─────────────────────
    # Tính mirror policy nếu chưa được pass vào
    if mirror_policy is None:
        from services.response_policy_v2 import compute_mirror_policy
        mirror_policy = compute_mirror_policy(
            emotion_ctx    = emotion_ctx    or {},
            intent_ctx     = intent_ctx     or {},
            internal_state = user_state     or {},
            presence       = presence       or {},
            policy         = policy         or {},
            message_len    = message_len,
            trust          = trust,
            momentum       = momentum,
        )

    mirror_block = build_mirror_prompt_block(mirror_policy)
    if mirror_block:
        parts.append(mirror_block)

    # ── [4] Pronoun ───────────────────────────────
    if pronoun_profile:
        ai_p   = pronoun_profile.get("ai_pronoun",   "mình")
        user_p = pronoun_profile.get("user_pronoun", "bạn")
        if ai_p != "mình" or user_p != "bạn":
            parts.append(f"Xưng: {ai_p} — gọi user: {user_p}.")

    # ── [5] Display name ──────────────────────────
    if display_name and display_name.lower() not in ("user", "bạn", ""):
        parts.append(f"Tên người dùng: {display_name}.")

    # ── [6] Memory — compact, max ~60 tokens ──────
    if memory_summary and len(memory_summary.strip()) > 10:
        mem = memory_summary.strip()
        # Hard cap: 240 chars ~ 60 tokens
        if len(mem) > 240:
            mem = mem[:237] + "..."
        parts.append(f"Ký ức về user:\n{mem}")

    # ── [7] Open loops — compact ──────────────────
    if relational_ctx:
        loops = relational_ctx.get("open_loops", [])
        if loops:
            loop_text = "; ".join(loops[:2])  # max 2 loops
            parts.append(f"Chủ đề còn bỏ ngỏ: {loop_text}")

    # ── [8] Life graph — chỉ inject nếu có signal ─
    if life_graph_summary:
        lg = life_graph_summary
        if isinstance(lg, dict):
            themes = lg.get("themes") or lg.get("key_points") or []
            if themes:
                t = "; ".join(str(x) for x in themes[:3])
                parts.append(f"Chủ đề cuộc đời: {t}")
        elif isinstance(lg, str) and len(lg.strip()) > 10:
            parts.append(f"Chủ đề cuộc đời: {lg.strip()[:120]}")

    # ── [9] Thread context — nếu có ──────────────
    if thread_context and len(thread_context.strip()) > 10:
        tc = thread_context.strip()[:200]
        parts.append(f"Thread hiện tại:\n{tc}")

    # ── [10] Advice gate — chỉ khi KHÔNG được phép
    # (mirror_block đã inject, nhưng nếu policy override allow → note)
    if policy.get("advice_allowed") and not mirror_policy.get("advice_allowed"):
        parts.append("Lượt này có thể đưa lời khuyên nếu user hỏi trực tiếp.")

    return "\n\n".join(p for p in parts if p and p.strip())


# --------------------------------------------------
# User prompt (giữ nguyên)
# --------------------------------------------------

def build_user_prompt(
    language: str,
    message:  str,
    context:  list[dict],
    hints:    str = "",
) -> str:
    return message.strip()


# --------------------------------------------------
# Messages payload (giữ nguyên)
# --------------------------------------------------

def build_messages_payload(
    system_prompt: str,
    user_prompt:   str,
) -> list[dict]:
    return [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_prompt},
    ]
