# --------------------------------------------------
# Trust Engine — MEBOST Hải Đăng V1.8
# --------------------------------------------------
# Trust = mức an toàn quan hệ giữa user và Hải Đăng.
# Khác với momentum (đà hội thoại) và pressure (áp lực tức thời).
# Trust tích luỹ chậm qua nhiều session — không thể spike nhanh.
#
# Flow mỗi turn:
#   load_trust(user_id)
#   signal = compute_trust_signal(message, emotion_ctx, momentum)
#   new_trust = blend(old, signal)
#   save → user_internal_state.trust
# --------------------------------------------------

from __future__ import annotations
import re

from db import get_db, utc_now_iso

# --------------------------------------------------
# Constants
# --------------------------------------------------

_DEFAULT_TRUST  = 0.30
_LEARN_RATE     = 0.10          # chậm hơn tone learning (0.15)
_TRUST_MIN      = 0.05
_TRUST_MAX      = 0.95

# Trust level bands
_BANDS = [
    (0.35, "cautious"),         # 0.00–0.35 → lắng nghe nhẹ nhàng
    (0.60, "warm"),             # 0.35–0.60 → người bạn ấm áp
    (0.80, "reflective"),       # 0.60–0.80 → hướng dẫn sâu hơn
    (1.01, "deep"),             # 0.80–1.00 → phản chiếu sâu
]

# Signal detection patterns
_VULNERABILITY = [
    "chưa nói với ai", "lần đầu mình kể", "mình sợ", "mình cô đơn",
    "mình thấy trống", "mình mệt lắm", "thật ra mình",
    "i've never told", "i'm scared", "i feel so alone",
    "i don't know why", "honestly", "i've been hiding",
]
_GRATITUDE = [
    "cảm ơn", "cảm ơn bạn", "mình cảm ơn", "bạn hiểu mình",
    "thank you", "thanks", "you understand", "that helped",
    "that means a lot",
]
_SHORT_REPLY_MAX = 30     # chars — dấu hiệu disengagement


# --------------------------------------------------
# Migration
# --------------------------------------------------

def ensure_trust_column() -> None:
    """Safe migration: thêm cột trust vào user_internal_state nếu chưa có."""
    try:
        db   = get_db()
        cols = [r[1] for r in db.execute(
            "PRAGMA table_info(user_internal_state)"
        ).fetchall()]
        if "trust" not in cols:
            db.execute(
                "ALTER TABLE user_internal_state "
                "ADD COLUMN trust REAL DEFAULT 0.30"
            )
            db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Load / Save
# --------------------------------------------------

def load_trust(user_id: str) -> float:
    try:
        db  = get_db()
        row = db.execute(
            "SELECT trust FROM user_internal_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row and row["trust"] is not None:
            return float(row["trust"])
    except Exception:
        pass
    return _DEFAULT_TRUST


def _save_trust(user_id: str, trust: float) -> None:
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_internal_state (user_id, trust, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 trust      = excluded.trust,
                 updated_at = excluded.updated_at""",
            (user_id, trust, utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Signal computation
# --------------------------------------------------

def compute_trust_signal(
    message: str,
    emotion_intensity: int,
    momentum: float,
) -> float:
    """
    Tính trust signal từ message hiện tại.
    Range [0, 1] — sẽ được blend với old_trust.

    Momentum scale: signal * (0.5 + momentum * 0.5)
    → momentum thấp → trust tăng chậm hơn
    → momentum cao  → trust tăng nhanh hơn
    """
    low = message.lower().strip()
    base = 0.0

    # Positive signals
    if any(kw in low for kw in _VULNERABILITY):
        base += 0.60
    if any(kw in low for kw in _GRATITUDE):
        base += 0.40
    if len(message.strip()) > 200:
        base += 0.25
    if emotion_intensity >= 7:
        base += 0.20

    # Negative signals
    if len(message.strip()) <= _SHORT_REPLY_MAX:
        base -= 0.20
    if re.search(r"^(ok|ừ|ok+|okk+|oke|bye|tạm biệt|\.+)$", low):
        base -= 0.15

    # Scale với momentum
    signal = base * (0.5 + momentum * 0.5)
    return round(max(-1.0, min(1.0, signal)), 3)


# --------------------------------------------------
# Update
# --------------------------------------------------

def update_trust_state(
    user_id: str,
    signal: float,
    old_trust: float | None = None,
) -> float:
    """
    Blend old_trust với signal, save, return new_trust.
    new = old * 0.90 + target * 0.10
    target = clamp(old + signal, 0.05, 0.95)
    """
    if old_trust is None:
        old_trust = load_trust(user_id)

    # Target: nudge từ signal
    target    = max(_TRUST_MIN, min(_TRUST_MAX, old_trust + signal))
    new_trust = old_trust * (1 - _LEARN_RATE) + target * _LEARN_RATE
    new_trust = round(max(_TRUST_MIN, min(_TRUST_MAX, new_trust)), 4)

    _save_trust(user_id, new_trust)
    return new_trust


# --------------------------------------------------
# Trust level interpretation
# --------------------------------------------------

def get_trust_level(trust: float) -> str:
    """cautious | warm | reflective | deep"""
    for threshold, label in _BANDS:
        if trust < threshold:
            return label
    return "deep"


def trust_prompt_hint(trust: float) -> str:
    level = get_trust_level(trust)
    if level == "cautious":
        return (
            "Mức tin tưởng còn thấp — giữ nhẹ nhàng, không đặt câu hỏi sâu, "
            "chỉ lắng nghe và phản chiếu nhẹ."
        )
    if level == "warm":
        return (
            "Mức tin tưởng đang hình thành — có thể hỏi nhẹ về cảm xúc, "
            "phản chiếu ấm áp, tránh các câu hỏi chạm vào vùng nhạy cảm."
        )
    if level == "reflective":
        return (
            "Mức tin tưởng tốt — có thể đặt câu hỏi sâu hơn, "
            "tham chiếu ký ức tự nhiên, giữ không gian rộng."
        )
    return (
        "Mức tin tưởng cao — phản chiếu sâu được phép, "
        "có thể đồng hành vào những vùng cảm xúc khó hơn."
    )
