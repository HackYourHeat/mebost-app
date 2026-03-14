"""
app.py — MEBOST Hải Đăng V2.3 (Runtime Guard + Production-safe Trace)

Runtime chính:
  emotion → intent → strategy(authority duy nhất) → memory_nodes → memory_selector → prompt → LLM

Gói 6.1 bổ sung:
  - runtime_guard điều khiển debug/trace theo env
  - /debug/turn có thể tắt hoàn toàn ở production
  - /chat?debug=true chỉ trả trace khi env cho phép
  - trace được cắt gọn / ẩn prompt tự động ở production
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, render_template, request, stream_with_context

load_dotenv()

from db import ensure_data_dir, get_db, init_db, utc_now_iso
from services.pipeline import (
    detect_emotion,
    detect_intent,
    select_strategy_with_reason,
    score_importance,
    compute_trust_delta,
    load_trust,
    update_trust,
    resolve_pronoun,
)
from services.memory_engine import (
    save_message_to_memory_with_reason,
    get_memory_nodes,
    get_memory_enabled,
    clear_memory,
    get_memory_runtime_snapshot,
)
from services.memory_selector import select_memory_with_trace
from services.prompt_builder import build_system_prompt, build_user_prompt, build_messages
from services.llm_adapter import generate_reply, generate_reply_stream, fallback_message
from services.user_service import ensure_user, ensure_session
from services.auth_engine import signup, login, logout, verify_email, get_account_info
from services.rate_limit_engine import check_rate_limit, RATE_LIMIT_PER_MINUTE
from services.context_engine import get_recent_context
from services.logging_engine import logger, log_exception
from services.turn_trace_engine import (
    TurnTrace,
    emotion_reason,
    intent_reason,
    importance_reason,
    trust_reason,
    pronoun_reason,
)
from services.runtime_guard import (
    is_production_env,
    should_allow_debug_route,
    should_expose_trace,
    safe_trace_payload,
    is_debug_turn_enabled,
    is_trace_in_chat_enabled,
)

MODEL_NAME = os.getenv("MODEL_NAME", "deepseek/deepseek-chat")
PIPELINE_VERSION = "v2.3-runtime-guard"
MAX_INPUT_CHARS = 6000

app = Flask(__name__, static_folder="static")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "mebost-dev-secret")

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
    pass


@app.before_request
def _startup():
    if not hasattr(app, "_initialized"):
        ensure_data_dir()
        init_db()
        app._initialized = True


# ── Helpers ────────────────────────────────────────────────────────────────

def normalize_language(lang: str) -> str:
    if not lang:
        return "Tiếng Việt"
    lang = lang.strip()
    aliases = {
        "vi": "Tiếng Việt",
        "vietnamese": "Tiếng Việt",
        "tiếng việt": "Tiếng Việt",
        "en": "English",
        "english": "English",
    }
    return aliases.get(lang.lower(), lang)


def ui_lang(language: str) -> str:
    return "vi" if "việt" in language.lower() else "en"


_TRUST_UPDATE_EVERY = 10


def _should_update_trust(user_id: str) -> bool:
    try:
        db = get_db()
        row = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'",
            (user_id,),
        ).fetchone()
        db.close()
        count = row[0] if row else 0
        return count > 0 and count % _TRUST_UPDATE_EVERY == 0
    except Exception:
        return False


def _save_ai_reply(ctx: dict, reply: str, response_time_ms: int) -> None:
    now = utc_now_iso()
    db = get_db()
    db.execute(
        """INSERT INTO messages
           (user_id, session_id, role, message_text, language, timestamp,
            response_time_ms, error_flag, memory_saved, deleted_by_user)
           VALUES (?, ?, 'assistant', ?, ?, ?, ?, 0, 0, 0)""",
        (ctx["user_id"], ctx["session_id"], reply, ctx["language"], now, response_time_ms),
    )
    db.commit()
    db.close()


def _finalize_trace(ctx: dict, reply: str, response_time_ms: int) -> None:
    trace = ctx.get("trace")
    if not trace:
        return
    trace.set_artifact("reply", reply)
    trace.set_artifact("response_time_ms", response_time_ms)


# ── Core pipeline ──────────────────────────────────────────────────────────

def _build_pipeline_context(body: dict):
    user_id = (body.get("user_id") or "").strip()
    session_id = (body.get("session_id") or "").strip()
    message = (body.get("message") or "").strip()
    language = normalize_language(body.get("language", "Tiếng Việt"))
    display_name = (body.get("display_name") or "").strip() or None
    device_hash = (body.get("device_hash") or "").strip() or None
    client_type = (body.get("client_type") or "web").strip()

    if not user_id or not session_id or not message:
        return None, (jsonify({"error": "user_id, session_id và message là bắt buộc."}), 400)
    if len(message) > MAX_INPUT_CHARS:
        return None, (
            jsonify({"error": f"Tin nhắn quá dài (tối đa {MAX_INPUT_CHARS} ký tự)."}),
            400,
        )

    lang_key = ui_lang(language)
    trace = TurnTrace(user_id=user_id, session_id=session_id, message=message, language=language)

    ensure_user(user_id, language, display_name=display_name, device_hash=device_hash)
    ensure_session(session_id, user_id, client_type)

    allowed, used_count = check_rate_limit(user_id)
    if not allowed:
        msg = {
            "vi": "Bạn đang nhắn quá nhanh. Hãy dừng lại một chút nhé 🌊",
            "en": "You're sending too fast. Take a breath 🌊",
        }[lang_key]
        return None, (jsonify({"error": msg, "used": used_count, "limit": RATE_LIMIT_PER_MINUTE}), 429)

    emotion, emotion_intensity = detect_emotion(message)
    intent = detect_intent(message)
    importance = score_importance(message, emotion_intensity)

    trace.add("emotion", {"emotion": emotion, "intensity": emotion_intensity}, emotion_reason(message, emotion, emotion_intensity))
    trace.add("intent", {"intent": intent}, intent_reason(message, intent))
    trace.add("importance", {"importance_score": importance}, importance_reason(message, importance))

    trust_before = load_trust(user_id)
    trust_after = trust_before
    trust_updated = False
    if _should_update_trust(user_id):
        delta = compute_trust_delta(message, emotion_intensity)
        trust_after = update_trust(user_id, delta)
        trust_updated = True
    trace.add(
        "trust",
        {"before": round(trust_before, 3), "after": round(trust_after, 3), "updated": trust_updated},
        trust_reason(trust_updated, trust_before, trust_after),
    )

    pronoun_ai, pronoun_user = resolve_pronoun(user_id, message)
    trace.add(
        "pronoun",
        {"ai_pronoun": pronoun_ai, "user_pronoun": pronoun_user},
        pronoun_reason(pronoun_ai, pronoun_user),
    )

    strategy, strategy_reason = select_strategy_with_reason(
        message=message,
        intent=intent,
        emotion=emotion,
        trust=trust_after,
    )
    trace.add("strategy", {"strategy": strategy}, strategy_reason)

    now = utc_now_iso()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """INSERT INTO messages
           (user_id, session_id, role, message_text, language, timestamp,
            error_flag, emotion_label, emotion_intensity, intent_label,
            importance_score, memory_saved, deleted_by_user)
           VALUES (?, ?, 'user', ?, ?, ?, 0, ?, ?, ?, ?, 0, 0)""",
        (
            user_id,
            session_id,
            message,
            language,
            now,
            emotion,
            emotion_intensity,
            intent,
            importance,
        ),
    )
    db.commit()
    user_msg_id = cur.lastrowid
    db.close()

    memory_saved = False
    memory_save_reason = "memory_disabled"
    saved_node_id = None
    if get_memory_enabled(user_id):
        memory_saved, memory_save_reason, saved_node_id = save_message_to_memory_with_reason(
            user_id,
            user_msg_id,
            message,
            importance,
        )

    raw_nodes = get_memory_nodes(user_id)
    memory_pick = select_memory_with_trace(raw_nodes, message, emotion)
    selected_mem = memory_pick["selected_text"]

    trace.add(
        "memory",
        {
            "memory_saved": memory_saved,
            "memory_save_reason": memory_save_reason,
            "saved_node_id": saved_node_id,
            "raw_node_count": len(raw_nodes),
            "selected_count": memory_pick["selected_count"],
            "selected_memory_chars": len(selected_mem),
            "candidate_count": memory_pick["candidate_count"],
        },
        memory_pick["reason"],
    )

    recent_context = get_recent_context(session_id, limit=4)
    trace.add("recent_context", {"chars": len(recent_context)}, "loaded recent session context")

    system_prompt = build_system_prompt(
        strategy=strategy,
        memory_text=selected_mem,
        pronoun_ai=pronoun_ai,
        pronoun_user=pronoun_user,
        display_name=display_name or "",
        language=language,
    )
    user_prompt = build_user_prompt(message, recent_context)
    messages_payload = build_messages(system_prompt, user_prompt)

    trace.set_artifact("recent_context", recent_context)
    trace.set_artifact("selected_memory", selected_mem)
    trace.set_artifact("memory_trace", memory_pick)
    trace.set_artifact("memory_runtime_snapshot", get_memory_runtime_snapshot(user_id))
    trace.set_artifact("system_prompt", system_prompt)
    trace.set_artifact("user_prompt", user_prompt)

    logger.info(
        "PIPELINE user=%s emotion=%s intent=%s strategy=%s trust=%.2f memory_saved=%s mem_nodes=%d selected=%d mem_chars=%d",
        user_id,
        emotion,
        intent,
        strategy,
        trust_after,
        memory_saved,
        len(raw_nodes),
        memory_pick["selected_count"],
        len(selected_mem),
    )

    return {
        "user_id": user_id,
        "session_id": session_id,
        "language": language,
        "lang_key": lang_key,
        "display_name": display_name,
        "user_msg_id": user_msg_id,
        "emotion": emotion,
        "emotion_intensity": emotion_intensity,
        "intent": intent,
        "strategy": strategy,
        "trust": trust_after,
        "messages_payload": messages_payload,
        "trace": trace,
    }, None


# ── Routes ─────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "model": MODEL_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "environment": "production" if is_production_env() else "development",
        "debug_turn_enabled": is_debug_turn_enabled(),
        "trace_in_chat_enabled": is_trace_in_chat_enabled(),
        "features": [
            "trace",
            "single_strategy_authority",
            "memory_runtime_slim",
            "memory_selector_trace",
            "pronoun",
            "trust",
            "runtime_guard",
        ],
    })


@app.route("/chat", methods=["POST"])
def chat():
    body = request.get_json(silent=True) or {}
    debug_requested = bool(body.get("debug", False))
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
    _finalize_trace(ctx, reply, response_time_ms)

    payload = {
        "reply": reply,
        "emotion": ctx["emotion"],
        "intent": ctx["intent"],
        "strategy": ctx["strategy"],
    }
    if should_expose_trace(debug_requested):
        payload["trace"] = safe_trace_payload(ctx["trace"].to_dict())
    return jsonify(payload)


@app.route("/debug/turn", methods=["POST"])
def debug_turn():
    if not should_allow_debug_route():
        abort(404)

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
    _finalize_trace(ctx, reply, response_time_ms)
    return jsonify(safe_trace_payload(ctx["trace"].to_dict()))


@app.route("/chat/stream", methods=["POST"])
def chat_stream():
    body = request.get_json(silent=True) or {}
    ctx, err = _build_pipeline_context(body)
    if err:
        return err

    t0 = time.time()

    def generate():
        collected: list[str] = []
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
            _finalize_trace(ctx, reply, response_time_ms)
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


@app.route("/memory/clear", methods=["POST"])
def memory_clear():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400
    count = clear_memory(user_id)
    return jsonify({"cleared": count})


@app.route("/memory/toggle", methods=["POST"])
def memory_toggle():
    body = request.get_json(silent=True) or {}
    user_id = (body.get("user_id") or "").strip()
    enabled = body.get("enabled", True)
    if not user_id:
        return jsonify({"error": "user_id bắt buộc"}), 400
    db = get_db()
    db.execute("UPDATE users SET memory_enabled = ? WHERE user_id = ?", (1 if enabled else 0, user_id))
    db.commit()
    db.close()
    return jsonify({"memory_enabled": bool(enabled)})


@app.route("/auth/signup", methods=["POST"])
def auth_signup():
    body = request.get_json(silent=True) or {}
    result = signup(
        email=(body.get("email") or "").strip(),
        password=(body.get("password") or ""),
        guest_user_id=(body.get("user_id") or "").strip(),
        ip=request.remote_addr or "unknown",
    )
    status = 200 if result.get("ok") else int(result.get("code", 400))
    return jsonify(result), status


@app.route("/auth/login", methods=["POST"])
def auth_login():
    body = request.get_json(silent=True) or {}
    result = login(
        email=(body.get("email") or "").strip(),
        password=(body.get("password") or ""),
    )
    status = 200 if result.get("ok") else int(result.get("code", 401))
    return jsonify(result), status


@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    result = logout()
    return jsonify(result)


@app.route("/auth/verify")
def auth_verify():
    token = (request.args.get("token") or "").strip()
    result = verify_email(token)
    status = 200 if result.get("ok") else int(result.get("code", 400))
    return jsonify(result), status


@app.route("/auth/me")
def auth_me():
    account_id = (request.args.get("account_id") or "").strip()
    if not account_id:
        return jsonify({"error": "account_id bắt buộc"}), 400
    result = get_account_info(account_id)
    status = 200 if result.get("ok") else int(result.get("code", 404))
    return jsonify(result), status


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=not is_production_env())
