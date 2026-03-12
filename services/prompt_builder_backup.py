# --------------------------------------------------
# Prompt Builder — MEBOST Hải Đăng V1.2
# Phong cách tâm sự: chậm, sâu, có nhịp, không dạy đời.
# --------------------------------------------------

# MAX input chars — dùng để trigger deep reflection
MAX_INPUT_CHARS = 5000

# --------------------------------------------------
# Identity
# --------------------------------------------------

_IDENTITY = """
Bạn là **Hải Đăng** — một người ngồi lắng nghe trong đêm.

Không phải chuyên gia. Không phải coach. Không phải bạn bè hời hợt.

Hải Đăng chiếu sáng để người dùng tự thấy đường —
không dẫn thay, không quyết định thay, không vội cứu.
""".strip()

# --------------------------------------------------
# Core language rules
# --------------------------------------------------

_CORE_RULES = """
Quy tắc ngôn ngữ (bắt buộc):
- Luôn trả lời đúng ngôn ngữ được yêu cầu.
- Không viết song ngữ.
- Không thêm bản dịch.
- Không đổi ngôn ngữ giữa chừng.
""".strip()

# --------------------------------------------------
# Style — nhịp điệu tâm sự
# --------------------------------------------------

_STYLE = """
Phong cách phản hồi:

Cấu trúc bắt buộc:
- Chia câu trả lời thành nhiều đoạn ngắn.
- Mỗi đoạn 1–2 câu.
- Có dòng trống giữa các đoạn.
- Tuyệt đối không viết khối text dày đặc.
- Tối đa 6 đoạn, trừ khi cảm xúc thật sự cần không gian hơn.

Thứ tự phản chiếu:
1. Nhận ra cảm xúc của người dùng trước.
2. Tạo khoảng lặng — không vội điền đầy.
3. Nếu cần, đặt một câu hỏi nhẹ để họ mở lòng thêm.

Nhịp điệu:
- Nói chậm.
- Không dồn nhiều ý trong một đoạn.
- Không cố tỏ ra thông minh.
- Không giảng giải.
""".strip()

# --------------------------------------------------
# Tone
# --------------------------------------------------

_TONE = """
Giọng điệu:
- Nhẹ nhàng, chậm rãi, ấm áp.
- Như người ngồi bên cạnh trong đêm yên tĩnh.
- Không ồn ào, không hối thúc.

Gọi tên:
- Nếu biết tên người dùng, thỉnh thoảng gọi tên — khi tự nhiên thôi.
- Không lặp tên trong mọi câu.
""".strip()

# --------------------------------------------------
# Negative constraints
# --------------------------------------------------

_NEGATIVE_CONSTRAINTS = """
Những điều Hải Đăng không được làm:

Câu sáo rỗng — tuyệt đối không dùng:
- "Tôi hiểu cảm giác của bạn."
- "Bạn nên tích cực lên."
- "Mọi chuyện rồi sẽ ổn thôi."
- "Bạn không đơn độc đâu."

Hành vi bị cấm:
- Không đưa lời khuyên nếu người dùng chưa hỏi.
- Không nhảy sang coach mode khi người dùng chỉ đang vent.
- Không cố giải quyết vấn đề ngay.
- Không nói như chuyên gia tâm lý.
- Không diễn cảm xúc giả.

Ưu tiên những câu như:
- "Nghe như chuyện này đang đè lên bạn khá nặng."
- "Có vẻ bạn đã mang điều này trong lòng khá lâu rồi."
- "Mình thấy ở đây có một lớp mệt rất sâu."
""".strip()

# --------------------------------------------------
# Policy constraints
# --------------------------------------------------

_POLICY_CONSTRAINTS = {
    "reflect_first": (
        "Lượt này bắt buộc phải phản chiếu cảm xúc trước. "
        "Không được đưa ra lời khuyên. Không được hỏi về giải pháp."
    ),
    "listen_only": (
        "Người dùng đang cần được lắng nghe — đang vent, đang xả. "
        "Chỉ phản chiếu và xác nhận cảm xúc. "
        "Không đưa ra bất kỳ lời khuyên hay câu hỏi hướng giải pháp nào."
    ),
    "supportive_help": (
        "Người dùng đang cần hỗ trợ nhẹ. "
        "Có thể gợi ý hướng suy nghĩ, nhưng nhẹ nhàng, không áp đặt."
    ),
    "deep_reflection": (
        "Người dùng đang tâm sự sâu hoặc viết nhiều. "
        "Đặt câu hỏi mở, chậm rãi, không vội kết luận. "
        "Có thể trả lời dài hơn — chia đoạn rõ, vẫn giữ nhịp chậm."
    ),
    "normal_companion": (
        "Đồng hành bình thường. Ấm áp, gần gũi, không vội."
    ),
}

# --------------------------------------------------
# Bio hints
# --------------------------------------------------

_BIO_HINTS = {
    "tense": (
        "Nhịp tim đang cao — phản hồi ngắn gọn, bình tĩnh. "
        "1–2 đoạn là đủ. Ưu tiên giảm áp lực."
    ),
    "attentive": (
        "Nhịp tim ổn định — phản hồi cân bằng, 2–3 đoạn."
    ),
    "calm": (
        "Nhịp tim thấp — không gian yên tĩnh. "
        "Có thể phản chiếu sâu hơn, 3–5 đoạn nếu phù hợp."
    ),
}

# --------------------------------------------------
# Reflection hints
# --------------------------------------------------

_REFLECTION_HINTS = {
    True:  "Lượt này cần phản chiếu sâu. Đừng vội trả lời — nhận ra cảm xúc trước.",
    False: "",
}


# --------------------------------------------------
# build_system_prompt
# --------------------------------------------------

def build_system_prompt(
    language: str,
    display_name: str = None,
    memory_summary: str = "",
    policy: dict = None,
    bio_state: dict = None,
    conscious_state: dict = None,
    life_graph_summary: dict = None,
    expressive_state: dict = None,
    message_len: int = 0,
    listening_style: str = "gentle_companion",
    tone_profile: dict = None,
    user_state: dict = None,
    personality: dict = None,
    conversation_turn: int = 0,
    momentum: float = 0.0,
    trust: float = 0.30,
    temporal_ctx: dict | None = None,
    gravity: float = 0.0,
    gravity_hook: str | None = None,
    echo_text: str | None = None,
    echo_strength: float = 0.0,
    distress: float = 0.0,
    pressure: float = 0.0,
    thread_context: str = "",
    pronoun_profile: dict | None = None,
    relational_ctx: dict | None = None,
    personality_dna: dict | None = None,
    familiarity: dict | None = None,
    presence: dict | None = None,
) -> str:
    """
    Tạo system prompt hoàn chỉnh cho Hải Đăng V1.3.

    Args:
        listening_style : quiet_listener | gentle_companion | reflective_guide
        tone_profile    : dict từ get_tone_profile()
        message_len     : len(message) — dùng để trigger deep reflection hint
    """
    parts = [
        _IDENTITY, "",
        f"Ngôn ngữ yêu cầu: {language}", "",
        _CORE_RULES, "",
        _STYLE, "",
        _TONE, "",
        _NEGATIVE_CONSTRAINTS,
    ]

    # Pronoun block (V2.3) — inject sớm để LLM nhận ngay
    if pronoun_profile:
        try:
            from services.pronoun_engine import pronoun_prompt_block
            p_block = pronoun_prompt_block(pronoun_profile)
            if p_block:
                parts += ["", p_block]
        except Exception:
            pass

    # Presence block (V3.1) — nhịp và độ mềm, inject sớm
    if presence:
        try:
            from services.presence_engine import presence_prompt_block as _ppb
            p_block = _ppb(presence)
            if p_block:
                parts += ["", p_block]
        except Exception:
            pass

    # Listening style block
    try:
        from services.listening_style_service import listening_style_prompt_block
        style_block = listening_style_prompt_block(listening_style)
        if style_block:
            parts += ["", style_block]
    except Exception:
        pass

    # Tone profile block
    if tone_profile:
        try:
            from services.adaptive_tone_engine import tone_profile_prompt_block
            tone_block = tone_profile_prompt_block(tone_profile)
            if tone_block:
                parts += ["", tone_block]
        except Exception:
            pass

    # User state inference hint
    if user_state:
        try:
            from services.user_state_engine import expression_hint
            state_hint = expression_hint(user_state)
            if state_hint:
                parts += ["", state_hint]
        except Exception:
            pass

    # Adaptive personality block
    if personality:
        try:
            from services.adaptive_personality_engine import personality_prompt_block
            pers_block = personality_prompt_block(personality)
            if pers_block:
                parts += ["", pers_block]
        except Exception:
            pass

    # Personality DNA block (V2.4) — cốt lõi ổn định, inject trước arbiter
    if personality_dna:
        try:
            from services.personality_dna_engine import dna_prompt_block
            dna_block = dna_prompt_block(personality_dna)
            if dna_block:
                parts += ["", dna_block]
        except Exception:
            pass

    # ── ARBITER: resolve conflicts before injecting ─────────
    try:
        from services.prompt_arbiter import ArbiterContext, arbitrate, depth_note
        _arc = ArbiterContext(
            trust=trust,
            momentum=momentum,
            gravity=gravity,
            echo_strength=echo_strength,
            emotion_intensity=int(emotion_intensity) if (emotion_intensity := getattr(policy, 'get', lambda k, d=None: d)('emotion_intensity', 0)) else 0,
            policy_mode=policy.get("mode", "normal_companion") if policy else "normal_companion",
            session_continuity=(temporal_ctx or {}).get("session_continuity", "continuous"),
            distress=distress,
            pressure=pressure,
        )
        _decision = arbitrate(_arc)
        _dn       = depth_note(_decision)
    except Exception:
        from services.prompt_arbiter import ArbiterDecision, depth_note
        _decision = ArbiterDecision()
        _dn       = ""

    # Override note — single authoritative direction
    if _decision.override_note:
        parts += ["", f"⚑ Ưu tiên lượt này: {_decision.override_note}"]

    # Depth note
    if _dn:
        parts += ["", _dn]

    # Emotional Echo — only if arbiter allows
    if _decision.inject_echo and echo_text and echo_strength >= 0.20:
        parts += [
            "",
            "Gợi ý phản chiếu cảm xúc (dùng hoặc diễn đạt lại theo ngữ cảnh):",
            echo_text,
        ]

    # Trust hint — always shown (gives context even when blocking depth)
    if _decision.inject_trust:
        try:
            from services.trust_engine import trust_prompt_hint as _tph
            parts += ["", _tph(trust)]
        except Exception:
            pass

    # Temporal hint
    try:
        from services.temporal_self_engine import temporal_prompt_hint as _teph
        if temporal_ctx:
            t_hint = _teph(temporal_ctx)
            if t_hint:
                parts += ["", t_hint]
    except Exception:
        pass

    # Gravity hint — only if arbiter allows
    if _decision.inject_gravity_hook:
        try:
            from services.conversation_gravity_engine import gravity_prompt_hint as _gph
            g_hint = _gph(gravity, gravity_hook)
            if g_hint:
                parts += ["", g_hint]
        except Exception:
            pass

    # Momentum hint — only if arbiter allows
    if _decision.inject_momentum:
        try:
            from services.momentum_engine import momentum_prompt_hint
            m_hint = momentum_prompt_hint(momentum)
            if m_hint:
                parts += ["", m_hint]
        except Exception:
            pass

    # Policy constraint
    if policy and policy.get("mode"):
        mode        = policy["mode"]
        constraint  = _POLICY_CONSTRAINTS.get(mode, "")
        advice_line = (
            "Tuyệt đối không đưa ra lời khuyên trong lượt này."
            if not policy.get("advice_allowed")
            else "Có thể gợi ý nhẹ nếu phù hợp."
        )
        if constraint:
            parts += ["", "Hướng dẫn phản hồi lượt này:", constraint, advice_line]

    # Deep reflection trigger khi message dài
    if message_len >= 600:
        parts += [
            "",
            f"Người dùng vừa viết một tin nhắn dài ({message_len} ký tự). "
            "Đây là lúc họ đang thật sự tâm sự. "
            "Hãy đọc kỹ, phản chiếu thật sự — không vội, không tóm tắt lại máy móc. "
            "Có thể trả lời dài hơn bình thường nhưng vẫn chia đoạn rõ ràng.",
        ]

    # Display name
    if display_name:
        parts += ["", f"Người dùng muốn được gọi là: {display_name}"]

    # Memory
    if memory_summary and memory_summary.strip():
        parts += [
            "",
            "Những điều Hải Đăng đã biết về người dùng:",
            memory_summary.strip(),
        ]

    # Memory threads (V2.2)
    if thread_context and thread_context.strip():
        parts += ["", thread_context]

    # Relational Continuity block (V3.0) — sau thread, trước bio
    if relational_ctx and relational_ctx.get("bond_stage", "new") != "new":
        try:
            from services.relational_continuity_engine import relational_prompt_block
            rel_block = relational_prompt_block(relational_ctx)
            if rel_block:
                parts += ["", rel_block]
        except Exception:
            pass

    # Familiarity block (V2.4) — cảm giác thân quen theo thời gian
    if familiarity:
        try:
            from services.familiarity_engine import familiarity_prompt_block
            fam_block = familiarity_prompt_block(familiarity)
            if fam_block:
                parts += ["", fam_block]
        except Exception:
            pass

    # Biological state hint
    if bio_state:
        try:
            from services.biological_engine import heartbeat_band
            band = heartbeat_band(bio_state)
            hint = _BIO_HINTS.get(band, "")
            if hint:
                parts += ["", "Nhịp nội tại lượt này:", hint]
        except Exception:
            pass

    # Consciousness reflection hint
    if conscious_state:
        reflection = conscious_state.get("reflection", {})
        needs      = reflection.get("needs_reflection", False)
        hint       = _REFLECTION_HINTS.get(needs, "")
        if hint:
            parts += ["", hint]

        mem_relevance = conscious_state.get("memory", {}).get("memory_relevance", 0.0)
        if mem_relevance >= 0.3:
            parts += [
                "",
                f"Ký ức liên quan đến tin nhắn này (mức {mem_relevance:.0%}). "
                "Có thể tự nhiên nhắc lại nếu phù hợp.",
            ]

    # Life Graph
    if life_graph_summary:
        threads = life_graph_summary.get("active_threads", [])
        nodes   = life_graph_summary.get("important_nodes", [])
        conns   = life_graph_summary.get("recent_connections", [])
        if threads or nodes:
            parts += ["", "Cấu trúc cuộc đời người dùng (Life Graph):"]
        if threads:
            parts += ["- Chủ đề đang hoạt động: " + ", ".join(threads)]
        if nodes:
            node_lines = "; ".join(
                f"{n['type']}: {n['label'][:30]}" for n in nodes[:4]
            )
            parts += [f"- Điểm quan trọng: {node_lines}"]
        if conns:
            parts += ["- Kết nối gần đây: " + " | ".join(conns[:2])]
        if threads or nodes:
            parts += [
                "Nếu phù hợp, có thể phản chiếu dựa trên những chủ đề này — "
                "chỉ khi tự nhiên, không gượng ép."
            ]

    # Expressive variance
    if expressive_state:
        try:
            from services.expressive_engine import expressive_prompt_block
            block = expressive_prompt_block(expressive_state)
            if block:
                parts += ["", "Nhịp điệu phản hồi lượt này:", block]
        except Exception:
            pass

    return "\n".join(parts)


# --------------------------------------------------
# build_user_prompt
# --------------------------------------------------

def build_user_prompt(
    language: str,
    message: str,
    recent_context: str = None,
    hints: str = "",
) -> str:
    context_block = recent_context.strip() if recent_context else "[no recent context]"
    hints_block   = f"{hints.strip()}\n\n" if hints and hints.strip() else ""

    return (
        f"Selected language: {language}\n"
        f"\n"
        f"User emotional state hint:\n"
        f"{hints_block}"
        f"Recent conversation context:\n"
        f"{context_block}\n"
        f"\n"
        f"Current user message:\n"
        f"{message}"
    )


# --------------------------------------------------
# build_messages_payload
# --------------------------------------------------

def build_messages_payload(system_prompt: str, user_prompt: str) -> list:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
