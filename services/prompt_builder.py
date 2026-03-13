# --------------------------------------------------
# Prompt Builder — MEBOST Hải Đăng V3.3
# --------------------------------------------------
# Target: ~300–400 tokens total (với memory)
#
# Block order:
#   [1] CORE_IDENTITY         — ~200t, bất biến
#   [2] Language              — ~10t
#   [3] Response strategy     — ~25t, điều khiển thật sự
#   [4] Mirror mode           — ~30t, nhường đường nếu strategy là guide/engage
#   [5] Anti-loop rules       — ~30t, luôn inject
#   [6] Presence + DNA        — ~20t, compact
#   [7] Pronoun               — ~10t
#   [8] Display name          — ~5t
#   [9] Memory                — ~60t max
#   [10] Open loops           — ~15t max
#   [11] Life graph           — ~15t max
# --------------------------------------------------

from __future__ import annotations

MAX_INPUT_CHARS = 5000

from services.response_policy_v2 import (
    CORE_IDENTITY,
    build_mirror_prompt_block,
)

# Anti-loop rules — luôn inject, ~30 tokens
_ANTI_LOOP = (
    "Không phản chiếu lặp quá 1–2 nhịp. "
    "Nếu strategy không phải reflect: tuyệt đối không mirror lại cảm xúc user. "
    "Nếu user xin giúp trực tiếp: đưa góc nhìn hoặc bước nhỏ cụ thể. "
    "Không chỉ hỏi ngược khi user đang tìm hướng. "
    "Không lặp lại cảm xúc của user như máy. "
    "Không mở đầu bằng 'Mình hiểu bạn đang...' trừ khi strategy là reflect."
)


def build_system_prompt(
    language:          str,
    display_name:      str,
    memory_summary:    str,
    policy:            dict,
    bio_state:         dict,
    conscious_state:   dict,
    life_graph_summary,
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
    mirror_policy:     dict | None = None,
    emotion_ctx:       dict | None = None,
    intent_ctx:        dict | None = None,
    strategy_hint:     str   = "",     # từ response_strategy_engine
    conv_state_block:  str   = "",     # từ conversation_state_engine
) -> str:

    parts: list[str] = []

    # ── [1] Core identity ─────────────────────────
    parts.append(CORE_IDENTITY)

    # ── [2] Language ──────────────────────────────
    if language and language.lower() not in ("tiếng việt", "vietnamese", "vi"):
        parts.append(f"Respond in: {language}")

    # ── [3] Response strategy (ưu tiên cao nhất) ─
    # Đây là chỉ dẫn điều khiển hành vi lượt này.
    # Nếu strategy là guide/engage → overrides mirror tendency.
    if strategy_hint:
        parts.append(strategy_hint)

    # ── [3b] Conversational RAM state ────────────────
    if conv_state_block:
        parts.append(conv_state_block)

    # ── [4] Mirror mode ───────────────────────────
    # Compute nếu chưa có
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

    # Chỉ inject mirror block nếu strategy KHÔNG phải guide/engage
    # (tránh mirror block mâu thuẫn với strategy)
    strategy_type = _extract_strategy(strategy_hint)
    # Mirror block CHỈ inject khi strategy == reflect.
    # guide / engage / comfort / reframe đều override mirror hoàn toàn.
    if strategy_type == "reflect":
        mirror_block = build_mirror_prompt_block(mirror_policy)
        if mirror_block:
            parts.append(mirror_block)

    # ── [5] Anti-loop rules ───────────────────────
    parts.append(_ANTI_LOOP)

    # ── [6] Presence + DNA compact ────────────────
    _presence_mode = (presence or {}).get("presence_mode", "steady")
    presence_hints = {
        "quiet":   "Hiện diện nhẹ nhàng — không đẩy, không kéo.",
        "close":   "Gần gũi và ấm hơn bình thường.",
        "holding": "Giữ chỗ — user đang mong manh. Ưu tiên an toàn.",
        "steady":  None,
    }
    if presence_hints.get(_presence_mode):
        parts.append(presence_hints[_presence_mode])

    # Personality DNA — compact
    if personality_dna:
        empathy  = personality_dna.get("empathy",   0.5)
        guidance = personality_dna.get("guidance",  0.5)
        if guidance > 0.55:
            parts.append("User phản hồi tốt với định hướng cụ thể — ưu tiên guide hơn câu hỏi.")
        elif empathy > 0.75:
            parts.append("User cần được cảm nhận trước — phản chiếu ấm trước khi suggest.")

    # Listening style compact
    _STYLE_HINTS = {
        "gentle_companion":  "Giọng ấm, nhịp chậm, không dồn dập.",
        "active_listener":   "Phản chiếu tích cực, xác nhận cảm xúc.",
        "direct_support":    "Rõ ràng, thực dụng, ít vòng vo.",
        "exploratory":       "Mở câu hỏi không gian — nhưng tối đa 1.",
    }
    style_hint = _STYLE_HINTS.get(listening_style or "gentle_companion")
    if style_hint:
        parts.append(style_hint)

    # ── [7] Pronoun ───────────────────────────────
    if pronoun_profile:
        ai_p   = pronoun_profile.get("ai_pronoun",   "mình")
        user_p = pronoun_profile.get("user_pronoun", "bạn")
        if ai_p != "mình" or user_p != "bạn":
            parts.append(f"Xưng: {ai_p} — gọi user: {user_p}.")

    # ── [8] Display name ──────────────────────────
    if display_name and display_name.lower() not in ("user", "bạn", ""):
        parts.append(f"Tên người dùng: {display_name}.")

    # ── [9] Memory — compact, max ~60 tokens ──────
    if memory_summary and len(memory_summary.strip()) > 10:
        mem = memory_summary.strip()
        if len(mem) > 240:
            mem = mem[:237] + "..."
        parts.append(f"Ký ức về user:\n{mem}")

    # ── [10] Open loops ───────────────────────────
    if relational_ctx:
        loops = relational_ctx.get("open_loops", [])
        if loops:
            loop_text = "; ".join(loops[:2])
            parts.append(f"Chủ đề còn bỏ ngỏ: {loop_text}")

    # ── [11] Life graph ───────────────────────────
    if life_graph_summary:
        lg = life_graph_summary
        if isinstance(lg, dict):
            themes = lg.get("themes") or lg.get("key_points") or []
            if themes:
                t = "; ".join(str(x) for x in themes[:3])
                parts.append(f"Chủ đề cuộc đời: {t}")
        elif isinstance(lg, str) and len(lg.strip()) > 10:
            parts.append(f"Chủ đề cuộc đời: {lg.strip()[:120]}")

    return "\n\n".join(p for p in parts if p and p.strip())


def _extract_strategy(hint: str) -> str:
    """Lấy strategy type từ hint string."""
    hint_lower = hint.lower()
    for s in ("guide", "engage", "comfort", "reframe", "reflect"):
        if s in hint_lower:
            return s
    return "reflect"


# --------------------------------------------------
# User prompt — compact nhưng có context
# --------------------------------------------------

def build_user_prompt(
    language: str,
    message:  str,
    context,          # str (từ get_recent_context) hoặc list[dict]
    hints:    str = "",
) -> str:
    """
    User prompt gọn: context gần nhất + hints + message.
    context có thể là str (formatted) hoặc list[dict].
    """
    parts = []

    # Recent context
    if context:
        if isinstance(context, str) and context.strip():
            # Trim nếu quá dài
            ctx = context.strip()
            if len(ctx) > 300:
                ctx = ctx[-300:]
            parts.append(f"Trước đó:\n{ctx}")
        elif isinstance(context, list):
            recent = context[-2:] if len(context) >= 2 else context
            ctx_lines = []
            for turn in recent:
                if not isinstance(turn, dict):
                    continue
                role = turn.get("role", "")
                text = (turn.get("content") or "").strip()
                if role and text:
                    label = "User" if role == "user" else "Hải Đăng"
                    if len(text) > 100:
                        text = text[:97] + "..."
                    ctx_lines.append(f"{label}: {text}")
            if ctx_lines:
                parts.append("Trước đó:\n" + "\n".join(ctx_lines))

    # Hints compact — 1 dòng có ý nghĩa
    if hints:
        first_hint = next((l.strip() for l in hints.split("\n") if l.strip()), "")
        if first_hint and len(first_hint) < 120:
            parts.append(f"[{first_hint}]")

    # Current message
    parts.append(message.strip())

    return "\n\n".join(parts)


# --------------------------------------------------
# Messages payload
# --------------------------------------------------

def build_messages_payload(
    system_prompt: str,
    user_prompt:   str,
) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
