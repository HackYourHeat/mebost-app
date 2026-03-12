# --------------------------------------------------
# Conversation Pattern Learning Engine — MEBOST V1.7
# --------------------------------------------------
# Học cách từng user muốn được lắng nghe,
# dựa trên lịch sử hội thoại thực tế — không dựa vào feedback tay.
#
# Learning loop:
#   analyze_patterns(user_id) → PatternMetrics
#   compute_tone_updates(metrics) → dict[field, new_value]
#   apply_gradual_update(user_id, updates)  ← slow, stable
#
# Chạy mỗi LEARN_EVERY_N messages (mặc định 10).
# Update chậm và ổn định: new = old * (1-RATE) + signal * RATE
# --------------------------------------------------

from __future__ import annotations
import re
from dataclasses import dataclass

from db import get_db, utc_now_iso

# --------------------------------------------------
# Config
# --------------------------------------------------

LEARN_EVERY_N  = 10      # học sau mỗi N messages của user
LEARN_WINDOW   = 30      # nhìn lại tối đa 30 messages gần nhất
LEARN_RATE     = 0.15    # tốc độ học — 10% mỗi chu kỳ

# Emotional language patterns
_EMOTIONAL_WORDS = [
    "mệt", "sợ", "buồn", "lo", "tức", "khóc", "cô đơn", "tuyệt vọng",
    "hạnh phúc", "vui", "nhớ", "đau", "trống", "mất",
    "sad", "tired", "scared", "lonely", "anxious", "happy", "miss",
    "afraid", "empty", "lost", "hurt",
]

_REFLECTIVE_WORDS = [
    "mình nghĩ", "mình cảm thấy", "mình nhận ra", "thật ra",
    "tại sao", "vì sao", "mình tự hỏi",
    "i think", "i feel", "i realize", "actually", "why", "i wonder",
]


# --------------------------------------------------
# Pattern Metrics
# --------------------------------------------------

@dataclass
class PatternMetrics:
    avg_user_msg_length:        float   # chars
    emotional_language_freq:    float   # 0–1
    reflective_language_freq:   float   # 0–1
    avg_ai_reply_length:        float   # chars
    topic_continuation_rate:    float   # 0–1 (user continues same topic)
    message_count:              int


def analyze_patterns(user_id: str, session_id: str | None = None) -> PatternMetrics | None:
    """
    Phân tích LEARN_WINDOW messages gần nhất của user.
    Trả về None nếu chưa đủ dữ liệu.
    """
    try:
        db = get_db()

        # User messages
        q = """SELECT message_text FROM messages
               WHERE user_id = ? AND role = 'user' AND deleted_by_user = 0
               ORDER BY id DESC LIMIT ?"""
        user_rows = db.execute(q, (user_id, LEARN_WINDOW)).fetchall()

        # AI replies (để đo avg_ai_reply_length)
        q2 = """SELECT message_text FROM messages
                WHERE user_id = ? AND role = 'assistant'
                ORDER BY id DESC LIMIT ?"""
        ai_rows = db.execute(q2, (user_id, LEARN_WINDOW)).fetchall()

        db.close()

        if len(user_rows) < 3:
            return None   # chưa đủ để học

        user_texts = [r["message_text"] or "" for r in user_rows]
        ai_texts   = [r["message_text"] or "" for r in ai_rows]

        # Avg message length
        avg_user_len = sum(len(t) for t in user_texts) / len(user_texts)
        avg_ai_len   = sum(len(t) for t in ai_texts) / len(ai_texts) if ai_texts else 0

        # Emotional language freq
        def _freq(texts, keywords):
            total = len(texts)
            hits  = sum(
                1 for t in texts
                if any(kw in t.lower() for kw in keywords)
            )
            return round(hits / total, 3) if total else 0.0

        emotional_freq  = _freq(user_texts, _EMOTIONAL_WORDS)
        reflective_freq = _freq(user_texts, _REFLECTIVE_WORDS)

        # Topic continuation — user message có dài hơn message trước không?
        # Proxy: tỉ lệ pairs mà len(t[i]) > len(t[i+1]) * 0.7
        continuation = 0
        for i in range(len(user_texts) - 1):
            if len(user_texts[i]) >= len(user_texts[i + 1]) * 0.7:
                continuation += 1
        cont_rate = round(continuation / max(len(user_texts) - 1, 1), 3)

        return PatternMetrics(
            avg_user_msg_length=round(avg_user_len, 1),
            emotional_language_freq=emotional_freq,
            reflective_language_freq=reflective_freq,
            avg_ai_reply_length=round(avg_ai_len, 1),
            topic_continuation_rate=cont_rate,
            message_count=len(user_rows),
        )

    except Exception:
        return None


# --------------------------------------------------
# Compute tone update signals
# --------------------------------------------------

def compute_tone_signals(metrics: PatternMetrics) -> dict[str, float]:
    """
    Chuyển PatternMetrics → signal [0,1] cho từng tone field.
    Đây là giá trị "mục tiêu" — không phải giá trị mới trực tiếp.
    """
    signals: dict[str, float] = {}

    # reply_length: dựa trên avg user message length
    if metrics.avg_user_msg_length > 300:
        signals["reply_length_target"] = 0.8    # → long
    elif metrics.avg_user_msg_length > 100:
        signals["reply_length_target"] = 0.5    # → medium
    else:
        signals["reply_length_target"] = 0.2    # → short

    # reflection_level: dựa trên emotional + reflective freq
    reflection_signal = (
        metrics.emotional_language_freq * 0.6
        + metrics.reflective_language_freq * 0.4
    )
    signals["reflection_level_target"] = round(reflection_signal, 3)

    # question_style: nếu user hay reflect → open questions tốt hơn
    signals["question_style_target"] = round(
        metrics.reflective_language_freq * 0.7
        + metrics.topic_continuation_rate * 0.3,
        3
    )

    # warmth_level: emotional language cao → cần ấm hơn
    signals["warmth_level_target"] = round(
        min(0.5 + metrics.emotional_language_freq * 0.5, 1.0), 3
    )

    return signals


# --------------------------------------------------
# Gradual update — slow learning
# --------------------------------------------------

_FIELD_SCALE: dict[str, tuple[str, str, str]] = {
    # signal_key: (tone_field, low_value, high_value)
    "reply_length_target":     ("reply_length",     "short", "long"),
    "reflection_level_target": ("reflection_level", "low",   "high"),
    "question_style_target":   ("question_style",   "minimal", "open"),
    "warmth_level_target":     ("warmth_level",     "neutral", "very_warm"),
}

_NUMERIC_MAP = {
    # reply_length
    "short":     0.15, "medium":    0.50, "long":      0.85,
    # reflection_level
    "low":       0.15,                    "high":       0.85,
    # question_style
    "minimal":   0.15, "gentle":    0.50, "open":      0.85,
    # warmth_level
    "neutral":   0.15, "warm":      0.55, "very_warm": 0.85,
    # advice_style (không học tự động, giữ nguyên)
    "ask_first": 0.20, "offer":     0.80,
}

_REVERSE_MAP: dict[str, list[tuple[float, str]]] = {
    "reply_length":     [(0.30, "short"),   (0.60, "medium"),   (1.01, "long")],
    "reflection_level": [(0.30, "low"),     (0.55, "medium"),   (1.01, "high")],
    "question_style":   [(0.30, "minimal"), (0.55, "gentle"),   (1.01, "open")],
    "warmth_level":     [(0.30, "neutral"), (0.55, "warm"),     (1.01, "very_warm")],
}


def _to_numeric(field: str, value: str) -> float:
    return _NUMERIC_MAP.get(value, 0.5)


def _to_label(field: str, numeric: float) -> str:
    for threshold, label in _REVERSE_MAP.get(field, []):
        if numeric < threshold:
            return label
    return "medium"


# Default starting numerics (mirror _to_numeric of defaults)
_DEFAULT_NUMERICS: dict[str, float] = {
    "reply_length":     0.50,
    "reflection_level": 0.50,
    "question_style":   0.50,
    "warmth_level":     0.55,
}


def _load_numerics(user_id: str) -> dict[str, float]:
    """Đọc numeric scores từ user_tone_numeric. Trả default nếu chưa có."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM user_tone_numeric WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()
        if row:
            return {
                "reply_length":     float(row["reply_length"]     or 0.50),
                "reflection_level": float(row["reflection_level"] or 0.50),
                "question_style":   float(row["question_style"]   or 0.50),
                "warmth_level":     float(row["warmth_level"]     or 0.55),
            }
    except Exception:
        pass
    return dict(_DEFAULT_NUMERICS)


def _save_numerics(user_id: str, nums: dict[str, float]) -> None:
    """Persist numeric scores."""
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_tone_numeric
               (user_id, reply_length, reflection_level, question_style, warmth_level, updated_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 reply_length     = excluded.reply_length,
                 reflection_level = excluded.reflection_level,
                 question_style   = excluded.question_style,
                 warmth_level     = excluded.warmth_level,
                 updated_at       = excluded.updated_at""",
            (user_id,
             nums["reply_length"], nums["reflection_level"],
             nums["question_style"], nums["warmth_level"],
             utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def apply_gradual_update(user_id: str, signals: dict[str, float]) -> dict[str, str]:
    """
    Load numeric scores → blend với signals → save numerics → update labels.
    new_numeric = old_numeric * (1 - LEARN_RATE) + target * LEARN_RATE

    Trả về dict các field label đã đổi.
    """
    from services.adaptive_tone_engine import get_tone_profile, update_tone_profile

    nums    = _load_numerics(user_id)
    current = get_tone_profile(user_id)
    updates: dict[str, str] = {}

    for signal_key, (field, _, _) in _FIELD_SCALE.items():
        target_numeric = signals.get(signal_key)
        if target_numeric is None:
            continue

        old_numeric = nums.get(field, _DEFAULT_NUMERICS.get(field, 0.5))
        new_numeric = old_numeric * (1 - LEARN_RATE) + target_numeric * LEARN_RATE
        nums[field] = round(new_numeric, 4)

        new_label = _to_label(field, new_numeric)
        old_label = current.get(field, "medium")
        if new_label != old_label:
            updates[field] = new_label

    _save_numerics(user_id, nums)
    if updates:
        update_tone_profile(user_id, updates)

    return updates


# --------------------------------------------------
# Main entry — gọi từ app.py
# --------------------------------------------------

def should_learn(user_id: str) -> bool:
    """True nếu user đã đủ LEARN_EVERY_N messages kể từ lần học cuối."""
    try:
        db    = get_db()
        count = db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'",
            (user_id,),
        ).fetchone()[0]
        db.close()
        return count > 0 and count % LEARN_EVERY_N == 0
    except Exception:
        return False


def run_pattern_learning(user_id: str) -> dict[str, str]:
    """
    Full pipeline: analyze → signals → gradual update.
    Trả về dict field đã đổi (empty nếu không đủ data).
    """
    metrics = analyze_patterns(user_id)
    if metrics is None:
        return {}

    signals = compute_tone_signals(metrics)
    updates = apply_gradual_update(user_id, signals)
    return updates
