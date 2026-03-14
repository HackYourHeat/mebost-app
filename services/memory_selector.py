"""
memory_selector.py — MEBOST Hải Đăng V2 (Clean)

Chọn memory thông minh để inject vào prompt.
Nguyên tắc: không inject hết — chọn đúng những gì liên quan đến lượt này.

3 lớp:
  1. identity   — tên, preference, boundary → luôn inject
  2. contextual — liên quan đến topic/emotion lượt này → inject nếu match
  3. recent     — tin nhắn gần nhất → inject để giữ mạch
"""
from __future__ import annotations
import re

MEMORY_CAP_CHARS = 1200  # ~300 tokens — đủ nhớ mà không chiếm hết context

_STOP_WORDS = {
    "và", "là", "của", "trong", "có", "không", "được", "với", "cho",
    "mình", "bạn", "tôi", "hay", "hoặc", "khi", "thì", "mà", "cũng",
    "đã", "sẽ", "đang", "rất", "cần", "nên", "muốn", "phải", "nếu",
    "the", "a", "an", "is", "are", "was", "to", "of", "in", "and", "i",
}

def _keywords(text: str) -> set[str]:
    words = set(re.findall(r"\b\w{3,}\b", text.lower()))
    return words - _STOP_WORDS

def _recency_score(node: dict) -> float:
    """0–1: node được access gần đây hơn thì điểm cao hơn."""
    try:
        from datetime import datetime, timezone
        last = node.get("last_used_at") or node.get("created_at") or ""
        if not last:
            return 0.2
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).days
        return max(0.0, 1.0 - days / 30.0)
    except Exception:
        return 0.2

def _relevance(node: dict, msg_kw: set[str], emotion: str) -> float:
    text = (node.get("memory_text") or "").lower()
    node_kw = _keywords(text)
    overlap = len(msg_kw & node_kw)
    kw_score = min(1.0, overlap / max(len(msg_kw), 1) * 2)

    emotion_match = 0.0
    _EMOTION_WORDS = {
        "sad":         ["buồn", "khóc", "mất", "thua", "thất"],
        "anxious":     ["lo", "sợ", "bất an", "áp lực", "stress"],
        "tired":       ["mệt", "kiệt", "chán", "trống"],
        "angry":       ["tức", "giận", "bực"],
    }
    for w in _EMOTION_WORDS.get(emotion, []):
        if w in text:
            emotion_match = 0.3
            break

    importance = min(1.0, float(node.get("importance_score") or 5) / 10)
    recency    = _recency_score(node)

    return kw_score * 0.5 + emotion_match * 0.2 + importance * 0.2 + recency * 0.1

def select_memory(
    nodes:   list[dict],
    message: str,
    emotion: str = "neutral",
) -> str:
    """
    Chọn và format memory để inject vào system prompt.
    Trả về string sạch, max ~300 tokens.
    """
    if not nodes:
        return ""

    msg_kw = _keywords(message)
    parts: list[str] = []
    used = 0

    # Layer 1: identity, preference, boundary — luôn inject
    core_types = {"identity", "preference", "boundary"}
    core_nodes = [n for n in nodes if n.get("memory_type") in core_types]
    for node in core_nodes[:5]:
        line = f"- {(node.get('memory_text') or '').strip()[:150]}"
        if used + len(line) > MEMORY_CAP_CHARS:
            break
        parts.append(line)
        used += len(line)

    # Layer 2: contextual — score theo relevance với lượt này
    other_nodes = [n for n in nodes if n.get("memory_type") not in core_types]
    scored = [(n, _relevance(n, msg_kw, emotion)) for n in other_nodes]
    scored.sort(key=lambda x: x[1], reverse=True)

    for node, score in scored:
        if score < 0.15:
            break
        line = f"- {(node.get('memory_text') or '').strip()[:150]}"
        if used + len(line) > MEMORY_CAP_CHARS:
            break
        parts.append(line)
        used += len(line)

    if not parts:
        return ""

    result = "\n".join(parts)
    if len(result) > MEMORY_CAP_CHARS:
        result = result[:MEMORY_CAP_CHARS - 3] + "..."
    return result
