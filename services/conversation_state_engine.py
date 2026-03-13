# --------------------------------------------------
# Conversation State Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Session-level conversational RAM.
# Không dùng DB — sống trong memory, reset theo session.
#
# 7 biến trạng thái:
#   current_need        — listen/comfort/guide/explore
#   temperature         — calm/heavy/fragile/open
#   relational_posture  — distant/neutral/close
#   stuck_level         — flowing/slightly_stuck/stuck
#   reflection_streak   — số lượt reflect liên tiếp
#   last_unresolved_pain — chủ đề đau chưa được xử lý
#   question_tolerance  — high/medium/low
#
# Update: rule-based, deterministic, không gọi LLM.
# Feed vào response_strategy_engine để override strategy.
# --------------------------------------------------

from __future__ import annotations
import threading

# In-memory store: session_id → ConvState dict
_STORE: dict[str, dict] = {}
_LOCK  = threading.Lock()

# --------------------------------------------------
# Default state
# --------------------------------------------------

def _default() -> dict:
    return {
        "current_need":         "listen",
        "temperature":          "calm",
        "relational_posture":   "neutral",
        "stuck_level":          "flowing",
        "reflection_streak":    0,
        "last_unresolved_pain": "",
        "question_tolerance":   "high",
    }


# --------------------------------------------------
# Public API
# --------------------------------------------------

def get_conv_state(session_id: str) -> dict:
    """Trả về conversational state của session. Tạo mới nếu chưa có."""
    with _LOCK:
        if session_id not in _STORE:
            _STORE[session_id] = _default()
        return dict(_STORE[session_id])  # trả bản copy


def update_conv_state(
    session_id:  str,
    message:     str,
    emotion_ctx: dict,
    intent_ctx:  dict,
    strategy:    str,          # strategy vừa chọn lượt này
    response:    str = "",     # reply của AI (nếu đã có)
) -> dict:
    """
    Cập nhật conversational state sau mỗi turn.
    Trả về state mới.
    """
    with _LOCK:
        state = _STORE.get(session_id, _default())
        state = _update(state, message, emotion_ctx, intent_ctx, strategy, response)
        _STORE[session_id] = state
        return dict(state)


def conv_state_prompt_block(state: dict) -> str:
    """
    Tạo block ngắn inject vào prompt (~25–40 tokens).
    Chỉ inject các field có signal thật sự.
    """
    if not state:
        return ""

    lines = []

    need  = state.get("current_need", "listen")
    temp  = state.get("temperature", "calm")
    streak = state.get("reflection_streak", 0)
    qtol  = state.get("question_tolerance", "high")
    stuck = state.get("stuck_level", "flowing")
    pain  = state.get("last_unresolved_pain", "")

    # Chỉ inject khi có signal đáng chú ý
    signals = []
    if temp in ("heavy", "fragile"):
        signals.append(f"temperature: {temp}")
    if stuck in ("slightly_stuck", "stuck"):
        signals.append(f"stuck: {stuck}")
    if streak >= 2:
        signals.append(f"reflection_streak: {streak} — đừng tiếp tục reflect")
    if qtol == "low":
        signals.append("question_tolerance: low — không hỏi thêm lượt này")
    if pain:
        signals.append(f"unresolved: {pain}")

    if not signals:
        return ""

    return "Trạng thái hội thoại: " + " | ".join(signals)


def clear_session(session_id: str) -> None:
    """Reset state khi session kết thúc hoặc user logout."""
    with _LOCK:
        _STORE.pop(session_id, None)


# --------------------------------------------------
# Core update logic
# --------------------------------------------------

def _update(
    state:       dict,
    message:     str,
    emotion_ctx: dict,
    intent_ctx:  dict,
    strategy:    str,
    response:    str,
) -> dict:
    state = dict(state)  # mutable copy

    emotion   = str(emotion_ctx.get("emotion",   "neutral")).lower()
    intensity = int(emotion_ctx.get("intensity", 5))
    intent    = str(intent_ctx.get("intent",     "talk")).lower()
    msg_lower = message.lower()

    # ── current_need ──────────────────────────────
    _self_attack = ["vô dụng","ăn bám","thất bại","tôi tệ","mình tệ","không xứng","tự trách"]
    if intent == "help" or "không biết làm gì" in msg_lower:
        state["current_need"] = "guide"
    elif any(p in msg_lower for p in _self_attack):
        # Self-attack ưu tiên trước vent — cần comfort không phải chỉ listen
        state["current_need"] = "comfort"
    elif intent == "vent":
        state["current_need"] = "listen"
    elif intent == "exploration":
        state["current_need"] = "explore"
    else:
        state["current_need"] = "listen"

    # ── temperature ───────────────────────────────
    if intensity >= 8 or emotion in ("overwhelmed", "desperate", "hopeless"):
        state["temperature"] = "fragile"
    elif intensity >= 6 or emotion in ("sad", "anxious", "angry", "tired"):
        state["temperature"] = "heavy"
    elif emotion in ("calm", "happy", "neutral") and intensity <= 4:
        state["temperature"] = "open" if intent == "exploration" else "calm"
    # Không reset nếu đang fragile — cần đủ calm turns để hạ nhiệt

    # ── stuck_level ───────────────────────────────
    _STUCK_WORDS = ["không biết", "bí", "không lối", "mắc kẹt", "stuck", "rối", "lost"]
    if any(w in msg_lower for w in _STUCK_WORDS):
        prev = state.get("stuck_level", "flowing")
        if prev == "flowing":
            state["stuck_level"] = "slightly_stuck"
        else:
            state["stuck_level"] = "stuck"
    elif strategy in ("guide",) and state.get("stuck_level") != "flowing":
        # AI đã guide → giảm stuck
        state["stuck_level"] = "flowing"

    # ── reflection_streak ─────────────────────────
    if strategy == "reflect":
        state["reflection_streak"] = state.get("reflection_streak", 0) + 1
    elif strategy in ("guide", "engage", "comfort", "reframe"):
        # AI đã thoát reflect → reset streak
        state["reflection_streak"] = 0

    # ── question_tolerance ────────────────────────
    _FRUSTRATION = ["bạn cứ hỏi", "hỏi ngược", "không giúp", "chỉ hỏi", "hỏi mãi"]
    if any(p in msg_lower for p in _FRUSTRATION):
        state["question_tolerance"] = "low"
    elif state.get("reflection_streak", 0) >= 2:
        state["question_tolerance"] = "low"
    elif state.get("reflection_streak", 0) == 1:
        state["question_tolerance"] = "medium"
    elif strategy in ("guide", "engage"):
        # AI đã switch mode → tolerance phục hồi
        state["question_tolerance"] = "medium"
    elif state.get("question_tolerance") == "low" and strategy not in ("reflect",):
        state["question_tolerance"] = "medium"

    # ── relational_posture ────────────────────────
    _CLOSE_WORDS = ["cảm ơn", "bạn hiểu mình", "mình cảm thấy được nghe", "thank"]
    if any(p in msg_lower for p in _CLOSE_WORDS):
        state["relational_posture"] = "close"
    elif state.get("temperature") == "fragile" and state.get("relational_posture") == "distant":
        state["relational_posture"] = "neutral"

    # ── last_unresolved_pain ──────────────────────
    _PAIN_MAP = {
        "self-worth":    ["vô dụng", "không xứng", "tệ", "ăn bám", "thất bại"],
        "family":        ["gia đình", "mẹ", "bố", "ba", "cha", "anh", "chị", "em"],
        "career":        ["công việc", "nghề", "sự nghiệp", "lương", "sếp", "đồng nghiệp"],
        "loneliness":    ["cô đơn", "một mình", "không ai", "cô độc"],
        "relationship":  ["người yêu", "bạn trai", "bạn gái", "yêu", "chia tay", "hôn nhân"],
    }
    for pain_label, keywords in _PAIN_MAP.items():
        if any(k in msg_lower for k in keywords):
            state["last_unresolved_pain"] = pain_label
            break

    return state


# --------------------------------------------------
# Strategy override từ conv state
# --------------------------------------------------

def conv_state_strategy_override(
    state:            dict,
    current_strategy: str,
) -> str:
    """
    Có thể override strategy dựa trên conversational state.
    Gọi sau select_strategy() để ensure state-aware behavior.
    """
    streak = state.get("reflection_streak", 0)
    qtol   = state.get("question_tolerance", "high")
    stuck  = state.get("stuck_level", "flowing")
    need   = state.get("current_need", "listen")

    # Đã reflect quá nhiều → buộc phải thoát
    if streak >= 3 and current_strategy == "reflect":
        return "engage"

    # Question tolerance thấp + đang reflect → switch
    if qtol == "low" and current_strategy == "reflect":
        return "engage"

    # Stuck + current strategy là reflect → guide
    if stuck == "stuck" and current_strategy == "reflect":
        return "guide"

    # current_need = comfort nhưng strategy là reflect → override
    if need == "comfort" and current_strategy == "reflect":
        return "comfort"

    return current_strategy
