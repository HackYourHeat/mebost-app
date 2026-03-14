"""
app.py — MEBOST Hải Đăng V2 (Clean)

Pipeline mới: 3 tầng rõ ràng.
Tầng 1 (mỗi request): emotion → intent → strategy → memory → prompt → LLM
Tầng 2 (conditional):  trust (mỗi 10 tin), pronoun (khi user đổi)
Tầng 3 (background):   memory_decay (route /admin/decay)
"""
import os
import time
import logging

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

load_dotenv()

from db import ensure_data_dir, get_db, init_db, utc_now_iso

from services.pipeline import (
    detect_emotion, detect_intent, select_strategy,
    score_importance, compute_trust_delta, load_trust, update_trust,
    resolve_pronoun,
)
from services.memory_engine import (
    save_message_to_memory, get_memory_nodes, get_memory_enabled, clear_memory,
)
from services.memory_selector import select_memory
from services.prompt_builder  import build_system_prompt, build_user_prompt, build_messages
from services.llm_adapter     import generate_reply, generate_reply_stream, fallback_message
from services.user_service    import ensure_user, ensure_session, get_user_profile
from services.auth_engine     import signup, login, logout, verify_email, get_account_info
from services.rate_limit_engine import check_rate_limit, RATE_LIMIT_PER_MINUTE
from services.context_engine    import get_recent_context
from services.logging_engine    import logger, log_exception

# ── Config ──────────────────────────────────────────────────────────────────

MODEL_NAME      = os.getenv("MODEL_NAME", "deepseek/deepseek-chat")
MAX_INPUT_CHARS = 6000

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "mebost-dev-secret")

try:
    from whitenoise import WhiteNoise
    _static = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(_static):
        app.wsgi_app = WhiteNoise(
            app.wsgi_app, root=_static, prefix="static",
            max_age=31536000, autorefresh=True,
        )
except ImportError:
    pass

# ── Startup ──────────────────────────────────────────────────────────────────

@app.before_request
def _startup():
    if not hasattr(app, "_initialized"):
        ensure_data_dir()
        init_db()
        app._initialized = True

# ── Helpers ──────────────────────────────────────────────────────────────────

def normalize_language(lang: str) -> str:
    if not lang:
        return "Tiếng Việt"
    lang = lang.strip()
    aliases = {"vi": "Tiếng Việt", "vietnamese": "Tiếng Việt", "tiếng việt": "Tiếng Việt",
               "en": "English", "english": "English"}
    return aliases.get(lang.lower(), lang)

def ui_lang(language: str) -> str:
    return "vi" if "việt" in language.lower() else "en"

_TRUST_UPDATE_EVERY = 10  # tin nhắn

def _should_update_trust(user_id: str) -> bool:
    """Chỉ update trust mỗi N tin nhắn để tránh ghi DB quá nhiều."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'",
            (user_id,),
        ).fetchone()
        db.close()
        count = row[0] if row else 0
        return count % _TRUST_UPDATE_EVERY == 0
    except Exception:
        return False

# ── Core chat pipeline ───────────────────────────────────────────────────────

def _build_pipeline_context(body: dict):
    user_id      = (body.get("user_id")      or "").strip()
    session_id   = (body.get("session_id")   or "").strip()
    message      = (body.get("message")      or "").strip()
    language     = normalize_language(body.get("language", "Tiếng Việt"))
    display_name = (body.get("display_name") or "").strip() or None
    device_hash  = (body.get("device_hash")  or "").strip() or None
    client_type  = (body.get("client_type")  or "web").strip()

    if not user_id or not session_id or not message:
        return None, (jsonify({"error": "user_id, session_id và message là bắt buộc."}), 400)
    if len(message) > MAX_INPUT_CHARS:
        return None, (jsonify({"error": f"Tin nhắn quá dài (tối đa {MAX_INPUT_CHARS} ký tự)."}), 400)

    lang_key = ui_lang(language)

    # Identity
    ensure_user(user_id, language, display_name=display_name, device_hash=device_hash)
    ensure_session(session_id, user_id, client_type)

    # Rate limit
    allowed, used_count = check_rate_limit(user_id)
    if not allowed:
        msg = {
            "vi": "Bạn đang nhắn quá nhanh. Hãy dừng lại một chút nhé 🌊",
            "en": "You're sending too fast. Take a breath 🌊",
        }[lang_key]
        return None, (jsonify({"error": msg, "used": used_count, "limit": RATE_LIMIT_PER_MINUTE}), 429)

    # ── Tầng 1: Perception (mỗi request) ─────────────────────────────────────
    emotion, emotion_intensity = detect_emotion(message)
    intent  = detect_intent(message)
    importance = score_importance(message, emotion_intensity)

    # ── Tầng 2a: Trust (conditional — mỗi 10 tin) ────────────────────────────
    trust = load_trust(user_id)
    if _should_update_trust(user_id):
        delta = compute_trust_delta(message, emotion_intensity)
        trust = update_trust(user_id, delta)

    # ── Tầng 2b: Pronoun (conditional — khi user đổi cách xưng) ──────────────
    pronoun_ai, pronoun_user = resolve_pronoun(user_id, message)

    # ── Strategy ──────────────────────────────────────────────────────────────
    strategy = select_strategy(intent, emotion, trust)

    # ── DB write: lưu message ─────────────────────────────────────────────────
    now = utc_now_iso()
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        """INSERT INTO messages
           (user_id, session_id, role, message_text, language, timestamp,
            error_flag, emotion_label, emotion_intensity, intent_label,
            importance_score, memory_saved, deleted_by_user)
           VALUES (?, ?, 'user', ?, ?, ?, 0, ?, ?, ?, ?, 0, 0)""",
        (user_id, session_id, message, language, now,
         emotion, emotion_intensity, intent, importance, 0),
    )
    db.commit()
    user_msg_id = cur.lastrowid
    db.close()

    # ── Memory: lưu tất cả tin nhắn thực sự ──────────────────────────────────
    memory_saved = False
    if get_memory_enabled(user_id):
        memory_saved = save_message_to_memory(
            user_id, user_msg_id, message, importance
        )

    # ── Memory: chọn để inject vào prompt ────────────────────────────────────
    raw_nodes     = get_memory_nodes(user_id)
    selected_mem  = select_memory(raw_nodes, message, emotion)

    # ── Recent context (session hiện tại) ────────────────────────────────────
    recent_context = get_recent_context(session_id, limit=4)

    # ── Build prompt ──────────────────────────────────────────────────────────
    system_prompt = build_system_prompt(
        strategy     = strategy,
        memory_text  = selected_mem,
        pronoun_ai   = pronoun_ai,
        pronoun_user = pronoun_user,
        display_name = display_name or "",
        language     = language,
    )
    user_prompt    = build_user_prompt(message, recent_context)
    messages_payload = build_messages(system_prompt, user_prompt)

    logger.info(
        "PIPELINE user=%s emotion=%s intent=%s strategy=%s trust=%.2f "
        "memory_saved=%s mem_nodes=%d mem_chars=%d",
        user_id, emotion, intent, strategy, trust,
        memory_saved, len(raw_nodes), len(selected_mem),
    )

    return {
        "user_id":          user_id,
        "session_id":       session_id,
        "language":         language,
        "lang_key":         lang_key,
        "display_name":     display_name,
        "user_msg_id":      user_msg_id,
        "emotion":          emotion,
        "emotion_intensity": emotion_intensity,
        "intent":           intent,
        "strategy":         strategy,
        "trust":            trust,
        "messages_payload": messages_payload,
    }, None


def _save_ai_reply(ctx: dict, reply: str, response_time_ms: int) -> None:
    now = utc_now_iso()
    db  = get_db()
    db.execute(
        """INSERT INTO messages
           (user_id, session_id, role, message_text, language, timestamp,
            response_time_ms, error_flag, memory_saved, deleted_by_user)
           VALUES (?, ?, 'assistant', ?, ?, ?, ?, 0, 0, 0)""",
        (ctx["user_id"], ctx["session_id"], reply, ctx["language"],
         now, response_time_ms),
    )
    db.commit()
    db.close()

# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health():
    return jsonify({"status": "ok", "model": MODEL_NAME})

@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    ctx, err = _build_pipeline_context(body)
    if err:
        return err

    t0 = time.time()
    try:
        reply = generate_reply(ctx["messages_payload"])
    except Exception as e:
        log_exception(ctx["user_id"], e)
        reply = fallback_message()

    response_time_ms = int((time.time() - t0) * 1000)
    _save_ai_reply(ctx, reply, response_time_ms)

    return jsonify({
        "reply":    reply,
        "emotion":  ctx["emotion"],
        "intent":   ctx["intent"],
        "strategy": ctx["strategy"],
    })

@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    body = request.get_json(silent=True) or {}
    ctx, err = _build_pipeline_context(body)
    if err:
        return err

    t0 = time.time()

    def generate():
        collected = []
        try:
            for chunk in generate_reply_stream(ctx["messages_payload"]):
                collected.append(chunk)
                yield f"data: {chunk}\n\n"
        except Exception as e:
            log_exception(ctx["user_id"], e)
            fallback = fallback_message()
            yield f"data: {fallback}\n\n"
            collected.append(fallback)
        finally:
            reply = "".join(collected)
            response_time_ms = int((time.time() - t0) * 1000)
            try:
                _save_ai_reply(ctx, reply, response_time_ms)
            except Exception:
                pass
        yield "data: [DONE]\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# ── Memory control ────────────────────────────────────────────────────────────

@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    body    = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400
    count = clear_memory(user_id)
    return jsonify({"cleared": count})

@app.route("/memory/toggle", methods=["POST"])
def memory_toggle():
    body    = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    enabled = body.get("enabled", True)
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400
    db = get_db()
    db.execute(
        "UPDATE users SET memory_enabled = ? WHERE user_id = ?",
        (1 if enabled else 0, user_id),
    )
    db.commit()
    db.close()
    return jsonify({"memory_enabled": bool(enabled)})

# ── Auth ──────────────────────────────────────────────────────────────────────

@app.route("/auth/signup", methods=["POST"])
def auth_signup():
    body = request.get_json(silent=True) or {}
    result = signup(
        email       = (body.get("email") or "").strip(),
        password    = (body.get("password") or ""),
        user_id     = (body.get("user_id") or "").strip(),
        ip_address  = request.remote_addr or "",
    )
    status = 200 if result.get("success") else 400
    return jsonify(result), status

@app.route("/auth/login", methods=["POST"])
def auth_login():
    body = request.get_json(silent=True) or {}
    result = login(
        email    = (body.get("email") or "").strip(),
        password = (body.get("password") or ""),
        user_id  = (body.get("user_id") or "").strip(),
    )
    status = 200 if result.get("success") else 401
    return jsonify(result), status

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    body = request.get_json(silent=True) or {}
    result = logout(user_id=(body.get("user_id") or "").strip())
    return jsonify(result)

@app.route("/auth/verify")
def auth_verify():
    token = request.args.get("token", "")
    result = verify_email(token)
    status = 200 if result.get("success") else 400
    return jsonify(result), status

@app.route("/auth/account")
def auth_account():
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400
    return jsonify(get_account_info(user_id))

# ── User info ─────────────────────────────────────────────────────────────────

@app.route("/user/profile")
def user_profile():
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400

    profile = get_user_profile(user_id)
    if not profile:
        return jsonify({"error": "User không tồn tại"}), 404

    db = get_db()
    msg_count = db.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
    ).fetchone()[0]
    mem_count = db.execute(
        "SELECT COUNT(*) FROM memory_nodes WHERE user_id = ? AND deleted_flag = 0",
        (user_id,),
    ).fetchone()[0]
    db.close()

    return jsonify({
        **profile,
        "total_messages": msg_count,
        "memory_nodes":   mem_count,
        "trust":          load_trust(user_id),
    })

# ── Admin ─────────────────────────────────────────────────────────────────────

ADMIN_KEY = os.getenv("ADMIN_KEY", "")

@app.route("/admin/decay", methods=["POST"])
def admin_decay():
    """Background job: giảm importance score của memory cũ."""
    key = request.headers.get("X-Admin-Key", "")
    if ADMIN_KEY and key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403

    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    db = get_db()
    cur = db.execute(
        """UPDATE memory_nodes
           SET importance_score = MAX(1, importance_score - 1)
           WHERE last_used_at < ? AND importance_score > 1 AND deleted_flag = 0""",
        (cutoff,),
    )
    count = cur.rowcount
    db.commit()
    db.close()

    logger.info("MEMORY_DECAY decayed=%d nodes", count)
    return jsonify({"decayed": count})

@app.route("/admin/health")
def admin_health():
    key = request.headers.get("X-Admin-Key", "")
    if ADMIN_KEY and key != ADMIN_KEY:
        return jsonify({"error": "unauthorized"}), 403

    db = get_db()
    users   = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    msgs    = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    memories = db.execute(
        "SELECT COUNT(*) FROM memory_nodes WHERE deleted_flag = 0"
    ).fetchone()[0]
    db.close()

    return jsonify({
        "status": "ok", "model": MODEL_NAME,
        "users": users, "messages": msgs, "active_memories": memories,
    })

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
