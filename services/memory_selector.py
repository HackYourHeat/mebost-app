# --------------------------------------------------
# Memory Selector — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Chuyển từ "memory accumulation" sang "memory selection".
#
# Nguyên tắc: chỉ inject memory tối thiểu cần thiết
# để phản hồi turn này tốt hơn RÕ RỆT.
#
# 4 layers:
#   identity    — 20–40t, gần như luôn inject
#   active_thread — 40–80t, nếu cùng mạch
#   deep_memory — 0–60t, chỉ khi semantic match rõ
#   state_summary — 20–40t, nén từ engine signals
#
# Target total: 80–180 tokens
# Hard cap:     200 tokens (~800 chars)
#
# Không gọi LLM. Stateless. Fail-safe.
# --------------------------------------------------

from __future__ import annotations

import re

# Hard cap toàn bộ memory block
MEMORY_HARD_CAP_CHARS = 800   # ~200 tokens

# Budget per layer (chars)
_BUDGET = {
    "identity":     160,   # ~40t
    "active_thread":320,   # ~80t
    "deep_memory":  240,   # ~60t
}

# Minimum relevance score để inject deep_memory
_DEEP_MEMORY_THRESHOLD = 0.35


# --------------------------------------------------
# Public API
# --------------------------------------------------

def select_memory(
    memory_nodes:   list[dict],
    thread_context: str,
    message:        str,
    emotion_ctx:    dict | None = None,
    intent_ctx:     dict | None = None,
    familiarity:    dict | None = None,
) -> str:
    """
    Chọn và format memory compact cho prompt injection.
    Trả về string sạch, max ~200 tokens.
    """
    try:
        return _select(
            memory_nodes   or [],
            thread_context or "",
            message        or "",
            emotion_ctx    or {},
            intent_ctx     or {},
            familiarity    or {},
        )
    except Exception:
        return ""


# --------------------------------------------------
# Core
# --------------------------------------------------

def _select(
    nodes:          list[dict],
    thread_context: str,
    message:        str,
    emotion_ctx:    dict,
    intent_ctx:     dict,
    familiarity:    dict,
) -> str:

    emotion = str(emotion_ctx.get("emotion", "neutral")).lower()
    intent  = str(intent_ctx.get("intent",  "talk")).lower()
    fam_lvl = str(familiarity.get("familiarity_level", "new"))

    msg_keywords = _extract_keywords(message)

    parts: list[str] = []
    total_chars = 0

    # ── Layer 1: Identity memory ──────────────────
    # Thông tin bền, xưng hô, self-pattern — luôn inject nếu có
    identity_nodes = _filter_by_type(nodes, ["identity", "preference", "name", "pronoun"])
    identity_text  = _format_layer(identity_nodes, _BUDGET["identity"], msg_keywords, min_score=0.0)
    if identity_text:
        parts.append(identity_text)
        total_chars += len(identity_text)

    # ── Layer 2: Active thread ────────────────────
    # Thread đang chạy — inject nếu match với message hiện tại
    if thread_context and len(thread_context.strip()) > 10:
        tc = thread_context.strip()
        # Check match: thread có liên quan đến message không?
        thread_keywords = _extract_keywords(tc)
        overlap = len(msg_keywords & thread_keywords)
        if overlap >= 1 or emotion in ("sad", "anxious", "tired", "overwhelmed", "heavy"):
            # Cap thread text
            if len(tc) > _BUDGET["active_thread"]:
                tc = tc[:_BUDGET["active_thread"] - 3] + "..."
            parts.append(f"Mạch đang tiếp tục: {tc}")
            total_chars += len(tc) + 22

    # ── Layer 3: Deep memory — chỉ khi match rõ ──
    remaining_budget = MEMORY_HARD_CAP_CHARS - total_chars
    if remaining_budget > 80:
        deep_nodes = _filter_by_type(
            nodes,
            ["emotional", "pattern", "relationship", "event", "insight"]
        )
        # Score từng node theo relevance với turn hiện tại
        scored = []
        for n in deep_nodes:
            score = _relevance_score(n, msg_keywords, emotion, intent)
            if score >= _DEEP_MEMORY_THRESHOLD:
                scored.append((score, n))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_nodes = [n for _, n in scored[:3]]  # max 3 items

        deep_text = _format_layer(
            top_nodes,
            min(_BUDGET["deep_memory"], remaining_budget - 40),
            msg_keywords,
            min_score=_DEEP_MEMORY_THRESHOLD,
        )
        if deep_text:
            parts.append(deep_text)
            total_chars += len(deep_text)

    # ── Assemble ──────────────────────────────────
    if not parts:
        return ""

    result = "\n".join(parts)

    # Final hard cap
    if len(result) > MEMORY_HARD_CAP_CHARS:
        result = result[:MEMORY_HARD_CAP_CHARS - 3] + "..."

    return result


def _format_layer(
    nodes:       list[dict],
    budget_chars:int,
    keywords:    set[str],
    min_score:   float = 0.0,
) -> str:
    """Format list nodes thành text compact."""
    if not nodes:
        return ""

    lines = []
    used  = 0

    for node in nodes:
        text = (node.get("memory_text") or "").strip()
        if not text:
            continue

        # Trim từng item
        if len(text) > 100:
            text = text[:97] + "..."

        line = f"- {text}"
        if used + len(line) > budget_chars:
            break

        lines.append(line)
        used += len(line) + 1

    return "\n".join(lines)


def _relevance_score(
    node:     dict,
    keywords: set[str],
    emotion:  str,
    intent:   str,
) -> float:
    """Score 0–1 cho relevance của một memory node với turn hiện tại."""

    text       = (node.get("memory_text") or "").lower()
    node_type  = (node.get("memory_type") or "").lower()
    importance = float(node.get("importance_score") or 0.5)
    recency    = _recency_score(node)

    # Keyword overlap
    node_keywords = _extract_keywords(text)
    overlap = len(keywords & node_keywords)
    keyword_score = min(1.0, overlap / max(len(keywords), 1) * 2)

    # Emotion match
    _EMOTION_WORDS = {
        "sad": ["buồn", "khóc", "mất", "thua", "thất"],
        "anxious": ["lo", "sợ", "bất an", "áp lực", "stress"],
        "tired": ["mệt", "kiệt", "chán", "vô vị", "trống"],
        "overwhelmed": ["quá tải", "ngộp", "không kịp", "chịu"],
    }
    emotion_match = 0.0
    for emo_word in _EMOTION_WORDS.get(emotion, []):
        if emo_word in text:
            emotion_match = 0.3
            break

    # Intent match
    intent_boost = 0.0
    if intent in ("seek_advice", "problem_solving") and node_type in ("pattern", "insight"):
        intent_boost = 0.2
    elif intent == "vent" and node_type == "emotional":
        intent_boost = 0.15

    score = (
        keyword_score  * 0.50 +
        importance     * 0.20 +
        recency        * 0.15 +
        emotion_match  * 0.10 +
        intent_boost   * 0.05
    )
    return min(1.0, score)


def _recency_score(node: dict) -> float:
    """0–1, cao hơn nếu node được access gần đây."""
    try:
        from datetime import datetime, timezone
        from db import utc_now_iso
        last = node.get("last_used_at") or node.get("created_at") or ""
        if not last:
            return 0.3
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_old = (now - dt).days
        return max(0.0, 1.0 - days_old / 30.0)
    except Exception:
        return 0.3


def _filter_by_type(nodes: list[dict], types: list[str]) -> list[dict]:
    return [n for n in nodes if (n.get("memory_type") or "").lower() in types]


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords — bỏ stopwords."""
    _STOP = {
        "và", "là", "của", "trong", "có", "không", "được", "với", "cho",
        "mình", "bạn", "tôi", "hay", "hoặc", "khi", "thì", "mà", "cũng",
        "đã", "sẽ", "đang", "rất", "cần", "nên", "muốn", "phải", "nếu",
        "the", "a", "an", "is", "are", "was", "to", "of", "in", "and",
    }
    words = set(re.findall(r'\b\w{3,}\b', text.lower()))
    return words - _STOP
