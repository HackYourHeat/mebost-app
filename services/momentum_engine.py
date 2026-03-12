# --------------------------------------------------
# Conversation Momentum Engine — MEBOST V1.6
# --------------------------------------------------
# Momentum = flow state của cuộc trò chuyện.
# Khác với emotion (cảm xúc hiện tại) và trust (mức tin tưởng).
# Đây là "đà" — user đang mở ra hay đóng lại?
#
# Flow:
#   load → decay (theo thời gian) → update → save
# --------------------------------------------------

from __future__ import annotations
import math
import re

from db import get_db, utc_now_iso

# --------------------------------------------------
# Constants
# --------------------------------------------------

_DEFAULT_MOMENTUM = 0.0
_DECAY_RATE       = 0.20   # per hour — giảm ~18% sau 1 giờ

# Openness keywords — dấu hiệu user đang mở lòng
_OPENNESS_HIGH = [
    "không biết mình đang sống vì điều gì",
    "đôi khi mình tự hỏi", "mình chưa nói với ai",
    "thật ra mình", "mình sợ", "mình cô đơn",
    "không ai hiểu", "mình không dám nói",
    "bây giờ mình mới nói", "lần đầu mình kể",
    "mình thấy trống rỗng", "mình mệt lắm rồi",
    "honestly", "i've never told anyone", "i'm scared",
    "i feel so alone", "i don't know why i'm still",
]
_OPENNESS_MED = [
    "mình hơi", "mình đang", "mình cảm thấy",
    "gần đây", "dạo này", "đôi khi",
    "i feel", "lately", "sometimes i",
    "i've been", "kind of",
]
_FIRST_PERSON = ["mình", "tôi", "tao", "i ", "i'm", "i've", "i was"]


# --------------------------------------------------
# Signal extractors
# --------------------------------------------------

def _message_length_factor(message: str) -> float:
    """0.2 (rất ngắn) → 1.0 (dài)."""
    n = len(message.strip())
    if n < 30:
        return 0.2
    if n < 100:
        return 0.4
    if n < 300:
        return 0.65
    if n < 600:
        return 0.85
    return 1.0


def _openness_factor(message: str) -> float:
    """0.0 → 1.0 — mức user đang mở lòng."""
    low = message.lower()

    if any(kw in low for kw in _OPENNESS_HIGH):
        return 1.0

    score = 0.0
    if any(kw in low for kw in _OPENNESS_MED):
        score += 0.4
    first_person_count = sum(low.count(fp) for fp in _FIRST_PERSON)
    score += min(first_person_count * 0.08, 0.4)

    # Câu hỏi tự vấn → reflective
    if re.search(r"(tại sao|vì sao|why|how come|làm sao mình)", low):
        score += 0.2

    return round(min(score, 1.0), 3)


# --------------------------------------------------
# Core update
# --------------------------------------------------

def compute_momentum(
    current_momentum: float,
    depth: float,
    trust: float,
    message: str,
) -> float:
    """
    Tính momentum mới từ state hiện tại + message.

    Formula:
        momentum = 0.35*depth + 0.25*trust
                 + 0.20*length_factor + 0.20*openness_factor

    Sau đó blend với current để tránh nhảy đột ngột:
        new = current * 0.4 + computed * 0.6
    """
    length_factor  = _message_length_factor(message)
    openness       = _openness_factor(message)

    computed = (
        0.35 * depth
        + 0.25 * trust
        + 0.20 * length_factor
        + 0.20 * openness
    )

    # Smooth — tránh spike đột ngột
    blended = current_momentum * 0.4 + computed * 0.6
    return round(min(1.0, max(0.0, blended)), 3)


def apply_momentum_decay(momentum: float, hours: float) -> float:
    """Exponential decay: momentum * exp(-0.20 * hours)."""
    hours = min(hours, 72)
    return round(momentum * math.exp(-_DECAY_RATE * hours), 3)


# --------------------------------------------------
# DB — add momentum column safely
# --------------------------------------------------

def ensure_momentum_column() -> None:
    """Safe migration: thêm cột momentum vào user_internal_state nếu chưa có."""
    try:
        db   = get_db()
        cols = [r[1] for r in db.execute(
            "PRAGMA table_info(user_internal_state)"
        ).fetchall()]
        if "momentum" not in cols:
            db.execute(
                "ALTER TABLE user_internal_state ADD COLUMN momentum REAL DEFAULT 0.0"
            )
            db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Load / Save
# --------------------------------------------------

def load_momentum(user_id: str) -> tuple[float, str]:
    """
    Trả về (momentum, updated_at_iso).
    updated_at dùng để tính decay.
    """
    try:
        db  = get_db()
        row = db.execute(
            "SELECT momentum, updated_at FROM user_internal_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row and row["momentum"] is not None:
            return float(row["momentum"]), str(row["updated_at"] or "")
    except Exception:
        pass
    return _DEFAULT_MOMENTUM, ""


def save_momentum(user_id: str, momentum: float) -> None:
    """Upsert momentum vào user_internal_state."""
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_internal_state (user_id, momentum, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 momentum   = excluded.momentum,
                 updated_at = excluded.updated_at""",
            (user_id, momentum, utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Full pipeline
# --------------------------------------------------

def compute_and_persist_momentum(
    user_id: str,
    message: str,
    depth: float,
    trust: float,
) -> float:
    """
    load → decay → update → save → return.
    Gọi trong app.py sau khi có internal_state.
    """
    from datetime import datetime, timezone

    raw_momentum, updated_at_str = load_momentum(user_id)

    # Time decay
    if updated_at_str:
        try:
            updated_at = datetime.fromisoformat(
                updated_at_str.replace("Z", "+00:00")
            )
            hours = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
            raw_momentum = apply_momentum_decay(raw_momentum, hours)
        except Exception:
            pass

    momentum = compute_momentum(raw_momentum, depth, trust, message)
    save_momentum(user_id, momentum)
    return momentum


# --------------------------------------------------
# Prompt hint
# --------------------------------------------------

def momentum_prompt_hint(momentum: float) -> str:
    """Chuyển momentum thành hướng dẫn hành vi cho prompt."""
    if momentum >= 0.70:
        return (
            "Đà cuộc trò chuyện đang cao — user đang mở lòng dần dần. "
            "Có thể đặt câu hỏi sâu hơn, phản chiếu chậm, "
            "giữ không gian rộng hơn cho từng câu trả lời."
        )
    if momentum >= 0.40:
        return (
            "Cuộc trò chuyện đang có nhịp — phản chiếu cân bằng, "
            "đừng vội chuyển chủ đề."
        )
    return (
        "Cuộc trò chuyện còn sơ khai — giữ nhẹ nhàng, "
        "không đặt câu hỏi quá sâu chưa."
    )
