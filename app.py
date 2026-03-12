import os
import time

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

from db import ensure_data_dir, get_db, init_db, migrate_db, migrate_accounts_schema, migrate_v13_schema, utc_now_iso

from services.user_service          import ensure_user, ensure_session, get_user_profile
from services.prompt_builder        import build_system_prompt, build_user_prompt, build_messages_payload
from services.llm_adapter           import generate_reply, generate_reply_stream, fallback_message
from services.emotion_engine        import build_emotion_context
from services.intent_engine         import build_intent_context
from services.context_engine        import get_recent_context
from services.importance_engine     import build_importance_context
from services.memory_engine            import save_memory_node
from services.memory_extraction_engine import build_memory_candidate
from services.memory_summary_engine import save_memory_summary, get_active_memory_summary
from services.memory_control_engine import get_memory_enabled, set_memory_enabled, forget_message, clear_memory
from services.memory_decay_engine   import decay_memory_nodes
from services.rate_limit_engine     import check_rate_limit, RATE_LIMIT_PER_MINUTE
from services.response_policy       import choose_response_policy, policy_hint
from services.biological_engine     import build_biological_state, load_bio_state, save_bio_state
from services.consciousness_engine  import build_consciousness_state, consciousness_to_policy_dict
from services.life_graph_engine     import process_life_graph
from services.expressive_engine     import compute_expressive_state
from services.auth_engine           import signup, login, logout, verify_email, get_account_info
from services.guest_cleanup_engine  import cleanup_expired_guests
from services.debug_engine          import build_health_payload, build_debug_payload
from services.listening_style_service import get_listening_style, set_listening_style, VALID_STYLES
from services.adaptive_tone_engine  import get_tone_profile, update_tone_profile, extract_tone_signals
from services.feedback_engine       import should_ask_feedback, get_feedback_prompt, save_feedback_prompt, count_ai_messages
from services.analytics_engine      import flush_analytics
from services.user_state_engine     import extract_signals, update_internal_state, expression_hint
from services.internal_state_service import compute_and_persist_state
from services.momentum_engine       import compute_and_persist_momentum, ensure_momentum_column
from services.temporal_self_engine   import compute_temporal_context, temporal_prompt_hint
from services.conversation_gravity_engine import compute_gravity, select_hook, gravity_prompt_hint
from services.emotional_echo_engine       import generate_echo
from services.pronoun_engine              import (
    ensure_pronoun_table, resolve_pronouns, set_pronoun_mode,
    get_pronoun_profile, MODES,
)
from services.memory_threading_engine     import (
    ensure_thread_link_table, get_active_threads, threads_prompt_block,
)
from services.trust_engine          import (
    ensure_trust_column, load_trust, compute_trust_signal,
    update_trust_state, get_trust_level, trust_prompt_hint,
)
from services.pattern_learning_engine import should_learn, run_pattern_learning
from services.adaptive_personality_engine import get_personality, learn_from_signals
from services.soul_dashboard        import build_soul_data, render_dashboard_html, ADMIN_KEY
from services.personality_dna_engine    import (
    ensure_dna_table, load_dna, update_dna_from_conversation,
)
from services.familiarity_engine        import compute_familiarity
from services.presence_engine           import compute_presence, presence_prompt_block
from services.memory_selector           import select_memory
from services.relational_continuity_engine import (
    compute_relational_continuity, continuity_prompt_hint,
)
from services.logging_engine        import (
    logger,
    log_chat_start, log_llm_call,
    log_chat_done, log_rate_limit_hit, log_exception,
    get_user_logger,
    ulog_request, ulog_analysis, ulog_memory, ulog_response, ulog_llm_error,
    ulog_memory_action,
)

# --------------------------------------------------
# Config
# --------------------------------------------------

load_dotenv()

MODEL_NAME      = os.getenv("MODEL_NAME", "deepseek/deepseek-chat")
MAX_INPUT_CHARS = 5000   # tâm sự tối đa — không reject trước ngưỡng này

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "mebost-dev-secret")

# WhiteNoise: serve static files nhanh tren Railway, khong qua gunicorn
try:
    from whitenoise import WhiteNoise
    _static = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(_static):
        app.wsgi_app = WhiteNoise(
            app.wsgi_app,
            root=_static,
            prefix="static",
            max_age=31536000,
            autorefresh=True,
        )
except ImportError:
    pass  # whitenoise chua install — Flask tu serve (local dev OK)

# --------------------------------------------------
# Helpers
# --------------------------------------------------

def normalize_language(lang: str) -> str:
    return lang.strip() if lang and lang.strip() else "Tiếng Việt"


def ui_lang(language: str) -> str:
    value = str(language or "").lower()
    if "vi" in value or "viet" in value or "vietnam" in value:
        return "vi"
    return "en"


def get_state_summary(user_id: str) -> dict:
    profile = get_user_profile(user_id)
    if not profile:
        return {}

    db = get_db()
    try:
        total_messages = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

        emotion_rows = db.execute(
            "SELECT emotion, timestamp FROM emotion_logs WHERE user_id = ? ORDER BY id DESC LIMIT 5",
            (user_id,),
        ).fetchall()

        recent_emotions = [{"emotion": r["emotion"], "timestamp": r["timestamp"]} for r in emotion_rows]
    finally:
        db.close()

    memory_summary = get_active_memory_summary(user_id)

    return {
        "user_id":          profile["user_id"],
        "display_name":     profile["display_name"],
        "language":         profile["language"],
        "memory_enabled":   profile["memory_enabled"],
        "created_at":       profile["created_at"],
        "total_messages":   total_messages,
        "recent_emotions":  recent_emotions,
        "memory_summary":   memory_summary,
        "is_guest":         profile.get("is_guest", 1),
        "account_id":       profile.get("account_id"),
        "guest_expires_at": profile.get("guest_expires_at"),
    }


def _build_pipeline_context(body: dict):
    """
    Shared pipeline — V2.3 clean order:
      perception → internal_state → momentum → trust →
      policy → personality → db_write → memory → echo/pronouns/gravity → prompt
    """
    user_id    = (body.get("user_id")    or "").strip()
    session_id = (body.get("session_id") or "").strip()
    message    = (body.get("message")    or "").strip()

    if not user_id or not session_id or not message:
        return None, (jsonify({"error": "user_id, session_id và message là bắt buộc."}), 400)
    if len(message) > MAX_INPUT_CHARS:
        return None, (jsonify({"error": f"Tin nhắn quá dài (tối đa {MAX_INPUT_CHARS} ký tự)."}), 400)

    message_len  = len(message)
    language     = normalize_language(body.get("language", "Tiếng Việt"))
    display_name = (body.get("display_name") or "").strip() or None
    device_hash  = (body.get("device_hash")  or "").strip() or None
    client_type  = (body.get("client_type")  or "web").strip()
    lang_key     = ui_lang(language)

    # Identity
    ensure_user(user_id, language, display_name=display_name, device_hash=device_hash)
    ensure_session(session_id, user_id, client_type)
    ulog_request(user_id, session_id, language, client_type, message)

    # Rate limit
    temporal_ctx        = compute_temporal_context(user_id)
    allowed, used_count = check_rate_limit(user_id)
    if not allowed:
        log_rate_limit_hit(user_id, used_count, RATE_LIMIT_PER_MINUTE)
        msg = {
            "vi": "Bạn đang nhắn quá nhanh. Hãy dừng lại một chút nhé 🌊",
            "en": "You're sending too fast. Take a breath 🌊",
        }[lang_key]
        return None, (jsonify({"error": msg, "used": used_count, "limit": RATE_LIMIT_PER_MINUTE}), 429)

    decay_memory_nodes(user_id)
    log_chat_start(user_id, session_id, message)

    # ── Layer 1: Perception ───────────────────────────────────
    emotion_ctx    = build_emotion_context(message)
    intent_ctx     = build_intent_context(message)
    importance_ctx = build_importance_context(message, emotion_ctx["intensity"])
    recent_context = get_recent_context(session_id, limit=3)
    memory_summary = get_active_memory_summary(user_id)

    # ── Layer 2: Internal state ───────────────────────────────
    previous_bio    = load_bio_state(user_id)
    bio_state       = build_biological_state(
        message, emotion_ctx["intensity"], previous_state=previous_bio,
    )
    conscious_state = build_consciousness_state(
        message, emotion_ctx, intent_ctx, memory_summary,
    )
    signals        = extract_signals(message)
    internal_state = compute_and_persist_state(user_id, signals)

    # ── Layer 3: Relationship dynamics ───────────────────────
    conversation_turn = count_ai_messages(session_id)
    momentum = compute_and_persist_momentum(
        user_id, message,
        depth=internal_state.get("depth", 0.0),
        trust=internal_state.get("trust", 0.30),
    )
    old_trust    = load_trust(user_id)
    trust_signal = compute_trust_signal(message, emotion_ctx["intensity"], momentum)
    trust        = update_trust_state(user_id, trust_signal, old_trust)

    # ── Layer 4: Policy (now has real momentum + trust) ───────
    policy = choose_response_policy(
        emotion_ctx["emotion"], emotion_ctx["intensity"],
        intent_ctx["intent"],
        message_len=message_len, momentum=momentum, trust=trust,
    )
    policy = consciousness_to_policy_dict(conscious_state)

    # ── Layer 5: Personality ──────────────────────────────────
    personality = learn_from_signals(
        user_id, signals, internal_state,
        emotion_ctx["intensity"], conversation_turn,
    )

    # ── Layer 5a: Personality DNA (V2.4) ─────────────────────
    personality_dna = update_dna_from_conversation(
        user_id       = user_id,
        message       = message,
        emotion       = emotion_ctx["emotion"],
        intent        = intent_ctx["intent"],
        internal_state= internal_state,
        conversation_turn = conversation_turn,
    )
    get_user_logger(user_id).info(
        "DNA_UPDATE empathy=%.3f reflection=%.3f guidance=%.3f warmth=%.3f q_freq=%.3f",
        personality_dna["empathy"], personality_dna["reflection_depth"],
        personality_dna["guidance_strength"], personality_dna["warmth"],
        personality_dna["question_freq"],
    )

    # ── Layer 5b: Familiarity (V2.4) ─────────────────────────
    familiarity = compute_familiarity(
        user_id          = user_id,
        trust            = trust,
        relationship_days= temporal_ctx.get("relationship_days", 0),
        momentum         = momentum,
    )
    get_user_logger(user_id).info(
        "FAMILIARITY level=%s msgs=%d callback=%.2f relaxation=%.2f",
        familiarity["familiarity_level"], familiarity["total_messages"],
        familiarity["callback_probability"], familiarity["tone_relaxation"],
    )

    listening_style  = get_listening_style(user_id)
    tone_profile     = get_tone_profile(user_id)
    expressive_state = compute_expressive_state(
        emotion_intensity=emotion_ctx["intensity"],
        conversation_depth=bio_state.get("conversation_depth", 0.0),
        trust_level=get_trust_level(trust),
        policy_mode=policy.get("mode", "normal_companion"),
        heartbeat_rate=bio_state.get("heartbeat_rate", 70),
    )

    # ── Layer 6: DB write ─────────────────────────────────────
    ulog_analysis(
        user_id,
        emotion_ctx["emotion"], emotion_ctx["intensity"],
        intent_ctx["intent"], importance_ctx["importance_score"],
        policy.get("mode", "normal_companion"),
    )
    db  = get_db()
    cur = db.cursor()
    now = utc_now_iso()
    cur.execute(
        "INSERT INTO emotion_logs (user_id, session_id, emotion, timestamp) VALUES (?,?,?,?)",
        (user_id, session_id, emotion_ctx["emotion"], now),
    )
    cur.execute(
        """INSERT INTO messages
           (user_id, session_id, role, message_text, language, timestamp,
            response_time_ms, error_flag,
            emotion_label, emotion_intensity, intent_label,
            importance_score, is_memory_candidate, memory_saved, deleted_by_user)
           VALUES (?,?,?,?,?,?,NULL,0,?,?,?,?,?,0,0)""",
        (
            user_id, session_id, "user", message, language, now,
            emotion_ctx["emotion"], emotion_ctx["intensity"],
            intent_ctx["intent"], importance_ctx["importance_score"],
            1 if importance_ctx["is_memory_candidate"] else 0,
        ),
    )
    db.commit()
    user_msg_id = cur.lastrowid

    # ── Layer 7: Memory + threading ──────────────────────────
    memory_saved = False
    if get_memory_enabled(user_id):
        candidate = build_memory_candidate(
            message, emotion_ctx["intensity"], importance_ctx["importance_score"],
        )
        if candidate:
            saved = save_memory_node(
                user_id, user_msg_id,
                candidate["memory_text"], candidate["importance_score"],
            )
            if saved:
                save_memory_summary(user_id)
                memory_saved = True
                memory_summary = get_active_memory_summary(user_id)
    ulog_memory(user_id, memory_saved, bool(memory_summary and memory_summary.strip()))
    active_threads     = get_active_threads(user_id)
    thread_prompt_text = threads_prompt_block(active_threads)
    life_graph_summary = process_life_graph(user_id, message)

    # ── Memory selection (V3.2) ──────────────────────────────
    # Lấy raw nodes để selector có thể score từng item
    from services.memory_summary_engine import get_active_memory_nodes
    raw_memory_nodes = get_active_memory_nodes(user_id)
    selected_memory = select_memory(
        memory_nodes   = raw_memory_nodes,
        thread_context = thread_prompt_text,
        message        = message,
        emotion_ctx    = emotion_ctx,
        intent_ctx     = intent_ctx,
        familiarity    = familiarity,
    )
    get_user_logger(user_id).info(
        "MEMORY_SEL nodes_in=%d chars_out=%d tokens=~%d",
        len(raw_memory_nodes), len(selected_memory), len(selected_memory)//4,
    )

    # ── Layer 8a: Relational Continuity (V3.0) ──────────────
    relational_ctx = compute_relational_continuity(
        user_id            = user_id,
        message            = message,
        temporal_ctx       = temporal_ctx,
        trust              = trust,
        momentum           = momentum,
        emotion_ctx        = emotion_ctx,
        internal_state     = internal_state,
        memory_summary     = memory_summary or "",
        life_graph_summary = life_graph_summary or {},
    )
    get_user_logger(user_id).info(
        "REL_CONT bond=%s arc=%s reentry=%s posture=%s continuity=%.3f loops=%s",
        relational_ctx["bond_stage"],
        relational_ctx["current_arc"] or "none",
        relational_ctx["reentry_style"],
        relational_ctx["companion_posture"],
        relational_ctx["continuity_score"],
        relational_ctx["open_loops"][:2] if relational_ctx["open_loops"] else [],
    )

    # ── Layer 8: Response shaping ─────────────────────────────
    echo_result     = generate_echo(emotion_ctx["emotion"], emotion_ctx["intensity"], momentum, trust)
    pronoun_profile = resolve_pronouns(user_id, message, trust=trust)
    gravity         = compute_gravity(momentum, trust, emotion_ctx["intensity"])
    hook            = select_hook(gravity, intent_ctx.get("intent", "vent"))

    # ── Layer 8b: Presence (V3.1) ───────────────────────────
    presence = compute_presence(
        emotion_ctx    = emotion_ctx,
        internal_state = internal_state,
        bio_state      = bio_state,
        momentum       = momentum,
        trust          = trust,
        gravity        = gravity,
        policy         = policy,
        temporal_ctx   = temporal_ctx,
        familiarity    = familiarity,
    )
    get_user_logger(user_id).info(
        "PRESENCE mode=%s pace=%s silence=%.2f q_pressure=%.2f softness=%.2f",
        presence["presence_mode"], presence["pace"],
        presence["silence_tolerance"], presence["question_pressure"],
        presence["softness_bias"],
    )

    # ── Pattern learning ──────────────────────────────────────
    if should_learn(user_id):
        _updates = run_pattern_learning(user_id)
        if _updates:
            get_user_logger(user_id).info("PATTERN_LEARN updates=%s", _updates)

    # ── Logging ───────────────────────────────────────────────
    get_user_logger(user_id).info(
        "ECHO emotion=%s intensity=%d strength=%.2f",
        emotion_ctx["emotion"], emotion_ctx["intensity"], echo_result["echo_strength"],
    )
    get_user_logger(user_id).info(
        "PRONOUN mode=%s ai=%s user=%s",
        pronoun_profile["pronoun_mode"],
        pronoun_profile["ai_pronoun"], pronoun_profile["user_pronoun"],
    )
    get_user_logger(user_id).info(
        "GRAVITY score=%.3f momentum=%.3f trust=%.3f",
        gravity, momentum, trust,
    )
    get_user_logger(user_id).info(
        "TRUST_UPDATE old=%.3f new=%.3f signal=%.3f level=%s",
        old_trust, trust, trust_signal, get_trust_level(trust),
    )

    # ── Layer 9: Prompt ───────────────────────────────────────
    from services.response_policy_v2 import compute_mirror_policy
    _mirror_policy = compute_mirror_policy(
        emotion_ctx    = emotion_ctx,
        intent_ctx     = intent_ctx,
        internal_state = internal_state,
        presence       = presence,
        policy         = policy,
        message_len    = message_len,
        trust          = trust,
        momentum       = momentum,
    )
    hints = "\n".join([emotion_ctx["hint"], intent_ctx["hint"], policy_hint(policy)])
    system_prompt    = build_system_prompt(
        language, display_name, selected_memory, policy,
        bio_state, conscious_state, life_graph_summary, expressive_state,
        message_len=message_len,
        listening_style=listening_style,
        tone_profile=tone_profile,
        user_state=internal_state,
        personality=personality,
        conversation_turn=conversation_turn,
        momentum=momentum,
        trust=trust,
        temporal_ctx=temporal_ctx,
        gravity=gravity,
        gravity_hook=hook,
        echo_text=echo_result["echo_text"],
        echo_strength=echo_result["echo_strength"],
        distress=signals.get("distress", 0.0),
        pressure=internal_state.get("pressure", 0.0),
        thread_context="",  # handled by memory_selector
        pronoun_profile=pronoun_profile,
        relational_ctx=relational_ctx,
        personality_dna=personality_dna,
        familiarity=familiarity,
        presence=presence,
        emotion_ctx=emotion_ctx,
        intent_ctx=intent_ctx,
        mirror_policy=_mirror_policy,
    )
    user_prompt      = build_user_prompt(language, message, recent_context, hints)
    messages_payload = build_messages_payload(system_prompt, user_prompt)
    db.close()

    ctx = {
        "user_id":            user_id,
        "session_id":         session_id,
        "language":           language,
        "display_name":       display_name,
        "lang_key":           lang_key,
        "emotion_ctx":        emotion_ctx,
        "intent_ctx":         intent_ctx,
        "bio_state":          bio_state,
        "conscious_state":    conscious_state,
        "life_graph_summary": life_graph_summary,
        "expressive_state":   expressive_state,
        "messages_payload":   messages_payload,
        # Production signal metrics
        "_prod_prompt_tokens": len(system_prompt) // 4,
        "_prod_mem_tokens":    len(selected_memory) // 4 if selected_memory else 0,
        "_prod_mirror_mode":   _mirror_policy.get("mirror_mode", "unknown"),
        "_prod_trust":         trust,
        "_prod_distress":      signals.get("distress", 0.0),
        "_prod_model":         MODEL_NAME,
    }
    return ctx, None


# --------------------------------------------------
# Routes — Static
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify(build_health_payload(MODEL_NAME))


@app.route("/debug")
def debug():
    return jsonify(build_debug_payload())


@app.route("/profile", methods=["POST"])
def profile():
    body         = request.get_json(silent=True) or {}
    user_id      = (body.get("user_id")      or "").strip()
    display_name = (body.get("display_name") or "").strip() or None
    language     = normalize_language(body.get("language", "Tiếng Việt"))
    device_hash  = (body.get("device_hash")  or "").strip() or None

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    ensure_user(user_id, language, display_name=display_name, device_hash=device_hash)
    return jsonify({"ok": True})

# --------------------------------------------------
# Routes — Data
# --------------------------------------------------

@app.route("/state/<user_id>")
def state(user_id):
    summary = get_state_summary(user_id)
    if not summary:
        # User chưa tồn tại → trả empty state thay vì 404
        return jsonify({"user_id": user_id, "exists": False})
    return jsonify(summary)


# --------------------------------------------------
# Routes — Auth
# --------------------------------------------------

@app.route("/auth/signup", methods=["POST"])
def auth_signup():
    body     = request.get_json(silent=True) or {}
    email    = body.get("email", "").strip()
    password = body.get("password", "")
    guest_id = body.get("user_id", "")
    ip       = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
    ip       = ip.split(",")[0].strip()

    # user_id tuỳ chọn — frontend có thể không gửi (guest flow)
    if not email or not password:
        return jsonify({"ok": False, "error": "Thiếu email hoặc password."}), 400
    if not guest_id:
        import uuid
        guest_id = "guest_" + uuid.uuid4().hex[:12]

    result = signup(email, password, guest_id, ip)

    if result["ok"]:
        # Gửi verification email
        try:
            from services.email_engine import send_verification_email
            send_verification_email(email, result.pop("verification_token"))
        except Exception as exc:
            app.logger.warning("email_send_failed: %s", exc)
            result.pop("verification_token", None)
        return jsonify(result), 201

    code = result.pop("code", 400)
    return jsonify(result), code


@app.route("/auth/login", methods=["POST"])
def auth_login():
    body     = request.get_json(silent=True) or {}
    email    = body.get("email", "").strip()
    password = body.get("password", "")

    if not email or not password:
        return jsonify({"ok": False, "error": "Thiếu email hoặc password."}), 400

    result = login(email, password)
    code   = result.pop("code", 200) if not result["ok"] else 200
    return jsonify(result), code


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    return jsonify(logout())


@app.route("/auth/verify")
def auth_verify():
    token  = request.args.get("token", "").strip()
    if not token:
        return jsonify({"ok": False, "error": "Thiếu token."}), 400
    result = verify_email(token)
    if result["ok"]:
        # Có thể redirect về frontend sau này
        return jsonify(result)
    code = result.pop("code", 400)
    return jsonify(result), code


@app.route("/messages/<session_id>")
def messages(session_id):
    db = get_db()
    try:
        rows = db.execute(
            """SELECT id, user_id, session_id, role, message_text, language, timestamp,
                      response_time_ms, error_flag, emotion_label, emotion_intensity,
                      intent_label, importance_score, is_memory_candidate,
                      memory_saved, deleted_by_user
               FROM messages WHERE session_id = ? ORDER BY id ASC""",
            (session_id,),
        ).fetchall()
        result = [dict(r) for r in rows]
    finally:
        db.close()
    return jsonify(result)

# --------------------------------------------------
# Routes — Memory controls
# --------------------------------------------------

@app.route("/memory/toggle", methods=["POST"])
def memory_toggle():
    body    = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    enabled = bool(body.get("enabled", True))
    set_memory_enabled(user_id, enabled)
    ulog_memory_action(user_id, f"memory_toggle enabled={enabled}")
    return jsonify({"ok": True, "memory_enabled": enabled})


@app.route("/memory/forget-message", methods=["POST"])
def memory_forget():
    body       = request.get_json(silent=True) or {}
    user_id    = (body.get("user_id") or "").strip()
    message_id = body.get("message_id")
    if not user_id or message_id is None:
        return jsonify({"error": "user_id and message_id required"}), 400
    forget_message(user_id, int(message_id))
    ulog_memory_action(user_id, "forget_message", target_id=int(message_id))
    return jsonify({"ok": True})


@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    body    = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    clear_memory(user_id)
    ulog_memory_action(user_id, "clear_memory")
    return jsonify({"ok": True})

# --------------------------------------------------
# Route — Chat (non-streaming, giữ từ V1)
# --------------------------------------------------

@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    lang_key = ui_lang(normalize_language(body.get("language", "Tiếng Việt")))

    db = None
    try:
        ctx, err = _build_pipeline_context(body)
        if err:
            return err

        t0               = time.time()
        reply            = generate_reply(ctx["messages_payload"])
        response_time_ms = int((time.time() - t0) * 1000)
        log_llm_call(MODEL_NAME, response_time_ms)

        # Adaptive tone — học từ message của user
        tone_signals = extract_tone_signals(body.get("message", ""))
        if tone_signals:
            update_tone_profile(ctx["user_id"], tone_signals)

        # Feedback injection — hỏi user sau mỗi 7 AI messages
        ai_count = count_ai_messages(ctx["session_id"])
        if should_ask_feedback(ctx["user_id"], ctx["session_id"]):
            fb_text = get_feedback_prompt(ctx["lang_key"])
            reply   = reply + fb_text
            save_feedback_prompt(ctx["user_id"], ctx["session_id"], ai_count + 1, fb_text)

        saved_at = utc_now_iso()
        db  = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO messages
               (user_id, session_id, role, message_text, language, timestamp,
                response_time_ms, error_flag,
                emotion_label, emotion_intensity, intent_label,
                importance_score, is_memory_candidate, memory_saved, deleted_by_user)
               VALUES (?,?,'assistant',?,?,?,?,0,?,?,?,0,0,0,0)""",
            (
                ctx["user_id"], ctx["session_id"], reply, ctx["language"], saved_at,
                response_time_ms,
                ctx["emotion_ctx"]["emotion"],
                ctx["emotion_ctx"]["intensity"],
                ctx["intent_ctx"]["intent"],
            ),
        )
        db.commit()
        db.close()
        db = None

        log_chat_done(
            ctx["user_id"], ctx["session_id"], response_time_ms,
            ctx["emotion_ctx"]["emotion"], ctx["intent_ctx"]["intent"],
        )
        ulog_response(ctx["user_id"], response_time_ms, len(reply))
        save_bio_state(ctx["user_id"], ctx["bio_state"])
        get_user_logger(ctx["user_id"]).info(
            "PROD_SIG model=%s prompt_t=%d mem_t=%d mode=%s llm_ms=%d total_ms=%d trust=%.2f distress=%.2f",
            ctx.get("_prod_model","?"),
            ctx.get("_prod_prompt_tokens", 0),
            ctx.get("_prod_mem_tokens", 0),
            ctx.get("_prod_mirror_mode","?"),
            response_time_ms,   # llm_ms not separately tracked in sync path
            response_time_ms,
            ctx.get("_prod_trust", 0.0),
            ctx.get("_prod_distress", 0.0),
        )

        return jsonify({
            "reply":            reply,
            "language":         ctx["language"],
            "emotion_label":    ctx["emotion_ctx"]["emotion"],
            "intent":           ctx["intent_ctx"]["intent"],
            "session_id":       ctx["session_id"],
            "saved_at":         saved_at,
            "response_time_ms": response_time_ms,
        })

    except Exception as e:
        log_exception("/chat", e)
        fallback = {
            "vi": "Đường kết nối đang gián đoạn… Nhưng Hải Đăng vẫn ở đây.",
            "en": "The connection is wavering… but Hải Đăng is still here.",
        }[lang_key]
        return jsonify({"reply": fallback, "error": True}), 500

    finally:
        if db is not None:
            db.close()

# --------------------------------------------------
# Route — Chat Stream (V1.1)
# --------------------------------------------------

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    body     = request.get_json(silent=True) or {}
    lang_key = ui_lang(normalize_language(body.get("language", "Tiếng Việt")))

    try:
        ctx, err = _build_pipeline_context(body)
        if err:
            # Trả lỗi dạng text để frontend stream reader vẫn đọc được
            status_code = err[1] if isinstance(err, tuple) else 500
            error_msg = {
                "vi": "Không thể kết nối. Thử lại nhé bạn.",
                "en": "Connection failed. Please try again.",
            }[lang_key]
            return Response(error_msg, status=status_code, mimetype="text/plain; charset=utf-8")

    except Exception as e:
        log_exception("/chat/stream setup", e)
        fallback = {
            "vi": "Đường kết nối đang gián đoạn… Nhưng Hải Đăng vẫn ở đây.",
            "en": "The connection is wavering… but Hải Đăng is still here.",
        }[lang_key]
        return Response(fallback, status=500, mimetype="text/plain; charset=utf-8")

    def generate():
        full_reply = []
        t0         = time.time()

        try:
            for chunk in generate_reply_stream(ctx["messages_payload"]):
                full_reply.append(chunk)
                yield chunk

        except Exception as e:
            log_exception("/chat/stream generate", e)
            ulog_llm_error(ctx["user_id"], str(e))
            fallback = fallback_message()
            full_reply.append(fallback)
            yield fallback

        # Sau stream xong → lưu assistant message
        response_time_ms = int((time.time() - t0) * 1000)
        reply_text       = "".join(full_reply)
        log_llm_call(MODEL_NAME, response_time_ms)
        ulog_response(ctx["user_id"], response_time_ms, len(reply_text))

        saved_at = utc_now_iso()
        db = None
        try:
            db  = get_db()
            cur = db.cursor()
            cur.execute(
                """INSERT INTO messages
                   (user_id, session_id, role, message_text, language, timestamp,
                    response_time_ms, error_flag,
                    emotion_label, emotion_intensity, intent_label,
                    importance_score, is_memory_candidate, memory_saved, deleted_by_user)
                   VALUES (?,?,'assistant',?,?,?,?,0,?,?,?,0,0,0,0)""",
                (
                    ctx["user_id"], ctx["session_id"], reply_text, ctx["language"], saved_at,
                    response_time_ms,
                    ctx["emotion_ctx"]["emotion"],
                    ctx["emotion_ctx"]["intensity"],
                    ctx["intent_ctx"]["intent"],
                ),
            )
            db.commit()
            log_chat_done(
                ctx["user_id"], ctx["session_id"], response_time_ms,
                ctx["emotion_ctx"]["emotion"], ctx["intent_ctx"]["intent"],
            )
            save_bio_state(ctx["user_id"], ctx["bio_state"])
        except Exception as e:
            log_exception("/chat/stream db", e)
        finally:
            if db is not None:
                db.close()

    return Response(
        stream_with_context(generate()),
        mimetype="text/plain; charset=utf-8",
    )

# --------------------------------------------------
# Routes — Listening Style (V1.3)
# --------------------------------------------------

@app.route("/user/style", methods=["GET"])
def get_user_style():
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    style = get_listening_style(user_id)
    return jsonify({"user_id": user_id, "listening_style": style})


@app.route("/user/style", methods=["POST"])
def set_user_style():
    body    = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    # chấp nhận cả 'style' lẫn 'listening_style' để tương thích frontend
    style   = (body.get("listening_style") or body.get("style") or "").strip()
    if not user_id or not style:
        return jsonify({"error": "user_id và style là bắt buộc"}), 400
    if style not in VALID_STYLES:
        return jsonify({"error": f"style không hợp lệ. Chọn: {', '.join(VALID_STYLES)}"}), 400
    ok = set_listening_style(user_id, style)
    if ok:
        ulog_memory_action(user_id, f"style_set={style}")
    return jsonify({"ok": ok, "listening_style": style})

# --------------------------------------------------
# Boot
# --------------------------------------------------

# -- Ensure directories exist (Railway + cPanel compatible)
import os as _os
for _d in ["logs", "logs/users", "logs/analytics", "data"]:
    _os.makedirs(_os.path.join(_os.path.dirname(__file__), _d), exist_ok=True)

ensure_data_dir()
init_db()
migrate_db()
migrate_accounts_schema()
migrate_v13_schema()
ensure_momentum_column()
ensure_trust_column()
ensure_thread_link_table()
ensure_pronoun_table()
ensure_dna_table()


@app.route("/user/pronouns", methods=["GET"])
def get_user_pronouns():
    user_id = request.args.get("user_id", "")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    profile = get_pronoun_profile(user_id)
    return jsonify({**profile, "available_modes": list(MODES.keys())})


@app.route("/user/pronouns", methods=["POST"])
def set_user_pronouns():
    data    = request.get_json(silent=True) or {}
    user_id = data.get("user_id", "")
    mode    = data.get("pronoun_mode", "neutral_default")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    profile = set_pronoun_mode(user_id, mode, source="user_selected")
    logger.info("PRONOUN_SET user=%s mode=%s", user_id, mode)
    return jsonify(profile)


# --------------------------------------------------
# Route — Soul Dashboard (admin ẩn)
# --------------------------------------------------

@app.route("/admin/soul")
def soul_dashboard():
    """
    Dashboard ẩn — chỉ ai biết ADMIN_KEY mới vào được.
    URL: /admin/soul?key=<ADMIN_KEY>
    Set ADMIN_KEY qua biến môi trường Railway.
    """
    key = request.args.get("key", "")
    if key != ADMIN_KEY:
        return jsonify({"error": "Forbidden"}), 403
    try:
        data = build_soul_data()
        fmt  = request.args.get("fmt", "html")
        if fmt == "json":
            return jsonify(data)
        return render_dashboard_html(data), 200, {"Content-Type": "text/html; charset=utf-8"}
    except Exception as e:
        log_exception("/admin/soul", e)
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(debug=True)
