# --------------------------------------------------
# memory_selector.py — MEBOST Hải Đăng V3.0 (Traceable)
# --------------------------------------------------
# Runtime chính chỉ chọn memory từ memory_nodes.
# Có trace để debug: candidate nào thắng, vì sao.
# --------------------------------------------------
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

MEMORY_CAP_CHARS = 1200
STOP_WORDS = {
    "và", "là", "của", "trong", "có", "không", "được", "với", "cho",
    "mình", "bạn", "tôi", "hay", "hoặc", "khi", "thì", "mà", "cũng",
    "đã", "sẽ", "đang", "rất", "cần", "nên", "muốn", "phải", "nếu",
    "the", "a", "an", "is", "are", "was", "to", "of", "in", "and", "i",
}
CORE_TYPES = {"identity", "preference", "boundary"}
_EMOTION_WORDS = {
    "sad": ["buồn", "khóc", "mất", "thua", "thất"],
    "anxious": ["lo", "sợ", "bất an", "áp lực", "stress"],
    "tired": ["mệt", "kiệt", "chán", "trống"],
    "angry": ["tức", "giận", "bực"],
}


def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"\b\w{3,}\b", text.lower()))
    return words - STOP_WORDS


def _recency_score(node: dict) -> float:
    try:
        last = node.get("last_used_at") or node.get("created_at") or ""
        if not last:
            return 0.2
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return max(0.0, 1.0 - days / 30.0)
    except Exception:
        return 0.2


def _score_candidate(node: dict, msg_kw: set[str], emotion: str) -> dict[str, Any]:
    text = (node.get("memory_text") or "").strip()
    text_low = text.lower()
    node_kw = _keywords(text)
    overlap_words = sorted(msg_kw & node_kw)
    overlap_count = len(overlap_words)
    kw_score = min(1.0, overlap_count / max(len(msg_kw), 1) * 2)

    emotion_match = 0.0
    matched_emotion_words: list[str] = []
    for w in _EMOTION_WORDS.get(emotion, []):
        if w in text_low:
            emotion_match = 0.3
            matched_emotion_words.append(w)

    importance = min(1.0, float(node.get("importance_score") or 5) / 10.0)
    recency = _recency_score(node)
    is_core = node.get("memory_type") in CORE_TYPES
    core_bonus = 0.25 if is_core else 0.0

    score = kw_score * 0.45 + emotion_match * 0.15 + importance * 0.20 + recency * 0.10 + core_bonus
    reasons: list[str] = []
    if is_core:
        reasons.append(f"core_type={node.get('memory_type')}")
    if overlap_count > 0:
        reasons.append(f"keyword_overlap={overlap_words[:5]}")
    if matched_emotion_words:
        reasons.append(f"emotion_match={matched_emotion_words[:3]}")
    reasons.append(f"importance={importance:.2f}")
    reasons.append(f"recency={recency:.2f}")

    return {
        "id": node.get("id"),
        "memory_type": node.get("memory_type") or "general",
        "memory_text": text[:150],
        "score": round(score, 4),
        "reasons": reasons,
        "is_core": is_core,
    }


def select_memory(nodes: list[dict], message: str, emotion: str = "neutral") -> str:
    return select_memory_with_trace(nodes, message, emotion)["selected_text"]


def select_memory_with_trace(
    nodes: list[dict],
    message: str,
    emotion: str = "neutral",
) -> dict[str, Any]:
    """
    Returns:
      {
        selected_text,
        selected_count,
        used_chars,
        candidate_count,
        top_candidates,
        reason,
      }
    """
    if not nodes:
        return {
            "selected_text": "",
            "selected_count": 0,
            "used_chars": 0,
            "candidate_count": 0,
            "top_candidates": [],
            "reason": "no_active_memory_nodes",
        }

    msg_kw = _keywords(message)
    scored = [_score_candidate(node, msg_kw, emotion) for node in nodes]
    scored.sort(key=lambda x: (x["is_core"], x["score"]), reverse=True)

    parts: list[str] = []
    used = 0
    selected: list[dict[str, Any]] = []

    for cand in scored:
        if not cand["is_core"] and cand["score"] < 0.15:
            continue
        line = f"- {cand['memory_text']}"
        if used + len(line) > MEMORY_CAP_CHARS:
            break
        parts.append(line)
        used += len(line)
        selected.append(cand)

    selected_text = "\n".join(parts)
    reason = "selected_from_ranked_candidates" if selected else "candidates_exist_but_none_passed_threshold"

    return {
        "selected_text": selected_text,
        "selected_count": len(selected),
        "used_chars": used,
        "candidate_count": len(scored),
        "top_candidates": scored[:8],
        "reason": reason,
    }
