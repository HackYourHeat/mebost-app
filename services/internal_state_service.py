# --------------------------------------------------
# Internal State Service — MEBOST Hải Đăng V1.5
# --------------------------------------------------
# Persist tâm lý nội tâm qua các turn và session.
#
# Flow mỗi turn:
#   load_state(user_id)          ← từ DB
#   apply_time_decay(state)      ← pressure mờ dần theo giờ
#   update_from_signals(state)   ← signals từ message hiện tại
#   save_state(user_id, state)   → vào DB
# --------------------------------------------------

from __future__ import annotations
import math
from datetime import datetime, timezone

from db import get_db, utc_now_iso

# --------------------------------------------------
# Defaults
# --------------------------------------------------

_DEFAULT_STATE: dict[str, float] = {
    "arousal":  0.0,
    "calm":     0.5,
    "pressure": 0.0,
    "trust":    0.3,
    "depth":    0.0,
}

# Decay rate per hour — pressure và arousal giảm tự nhiên
# depth và trust giảm chậm hơn
_DECAY_RATES: dict[str, float] = {
    "pressure": 0.35,   # giảm ~30% sau 1 giờ
    "arousal":  0.25,
    "calm":     0.08,   # calm giảm rất chậm
    "trust":    0.04,   # trust rất bền vững
    "depth":    0.15,
}

# Signal weights — mức ảnh hưởng của từng signal lên state
_SIGNAL_WEIGHTS: dict[str, dict[str, float]] = {
    # signal_name: {state_field: delta_weight}
    "distress":     {"pressure": +0.45, "calm": -0.25, "arousal": +0.20},
    "safety":       {"calm":     +0.35, "pressure": -0.20, "trust": +0.10},
    "overload":     {"arousal":  +0.35, "depth": -0.10, "pressure": +0.15},
    "salience":     {"depth":    +0.25, "trust": +0.05},
    "clarity":      {"calm":     +0.20, "depth": +0.10},
    "help_seeking": {"trust":    +0.10, "pressure": -0.05},
}


# --------------------------------------------------
# Load
# --------------------------------------------------

def load_state(user_id: str) -> dict[str, float]:
    """
    Đọc internal state từ DB.
    Nếu chưa có → trả về default state.
    """
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM user_internal_state WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()
        if row:
            return {
                "arousal":    float(row["arousal"]  or 0.0),
                "calm":       float(row["calm"]     or 0.5),
                "pressure":   float(row["pressure"] or 0.0),
                "trust":      float(row["trust"]    or 0.3),
                "depth":      float(row["depth"]    or 0.0),
                "_updated_at": str(row["updated_at"] or ""),
            }
    except Exception:
        pass
    return dict(_DEFAULT_STATE)


# --------------------------------------------------
# Time decay
# --------------------------------------------------

def apply_time_decay(state: dict[str, float]) -> dict[str, float]:
    """
    Giảm state theo thời gian thực đã trôi qua.
    Dùng exponential decay: value *= exp(-rate * hours)

    Nếu không có _updated_at → skip decay.
    """
    updated_at_str = state.get("_updated_at", "")
    if not updated_at_str:
        return state

    try:
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        now        = datetime.now(timezone.utc)
        hours      = (now - updated_at).total_seconds() / 3600.0
        hours      = min(hours, 72)  # cap ở 72h — không decay vô hạn
    except Exception:
        return state

    decayed = dict(state)
    for field, rate in _DECAY_RATES.items():
        if field in decayed:
            decayed[field] = round(decayed[field] * math.exp(-rate * hours), 3)

    return decayed


# --------------------------------------------------
# Update from signals
# --------------------------------------------------

def update_from_signals(
    state: dict[str, float],
    signals: dict[str, float],
) -> dict[str, float]:
    """
    Cập nhật state từ signals của message hiện tại.
    Mỗi signal tác động lên nhiều chiều state theo _SIGNAL_WEIGHTS.
    """
    updated = dict(state)

    for signal_name, signal_value in signals.items():
        if signal_value <= 0:
            continue
        weights = _SIGNAL_WEIGHTS.get(signal_name, {})
        for field, weight in weights.items():
            if field in updated:
                updated[field] = updated[field] + signal_value * weight

    # Clamp [0, 1]
    for field in _DEFAULT_STATE:
        if field in updated:
            updated[field] = round(min(1.0, max(0.0, updated[field])), 3)

    return updated


# --------------------------------------------------
# Save
# --------------------------------------------------

def save_state(user_id: str, state: dict[str, float]) -> None:
    """Lưu internal state vào DB."""
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_internal_state
               (user_id, arousal, calm, pressure, trust, depth, updated_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 arousal    = excluded.arousal,
                 calm       = excluded.calm,
                 pressure   = excluded.pressure,
                 trust      = excluded.trust,
                 depth      = excluded.depth,
                 updated_at = excluded.updated_at""",
            (
                user_id,
                state.get("arousal",  0.0),
                state.get("calm",     0.5),
                state.get("pressure", 0.0),
                state.get("trust",    0.3),
                state.get("depth",    0.0),
                utc_now_iso(),
            ),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Full pipeline — convenience function
# --------------------------------------------------

def compute_and_persist_state(
    user_id: str,
    signals: dict[str, float],
) -> dict[str, float]:
    """
    Convenience: load → decay → update → save → return.
    Dùng trong app.py thay cho update_internal_state() cũ.
    """
    state = load_state(user_id)
    state = apply_time_decay(state)
    state = update_from_signals(state, signals)
    save_state(user_id, state)
    return state
