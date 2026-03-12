# --------------------------------------------------
# Biological Engine — MEBOST Hải Đăng V1.1
# Homeostatic agent architecture.
# Không phải AI có cảm xúc thật —
# đây là internal rhythm và state regulation.
# --------------------------------------------------

from __future__ import annotations
import math
import random

# --------------------------------------------------
# Constants
# --------------------------------------------------

_DEFAULT_STATE: dict = {
    "heartbeat_rate":      70,
    "breath_phase":        "inhale",
    "text_pressure":       0.0,
    "emotional_heat":      0.0,
    "conversation_depth":  0.0,
}

_BREATH_CYCLE = ("inhale", "hold", "exhale")

# Heartbeat bands
_HB_CALM_MAX    = 70   # ≤ 70  → calm, reflective
_HB_TENSE_MIN   = 80   # ≥ 80  → tense, short responses
_HB_MIN         = 60
_HB_MAX         = 100
_HRV_BASE       = 2.5   # baseline variability ±bpm


# --------------------------------------------------
# 1. Digital Heartbeat
# --------------------------------------------------

def adjust_heartbeat(
    emotion_intensity: int,
    text_pressure: float,
    previous_rate: int = 70,
    apply_hrv: bool = True,
) -> int:
    """
    Điều chỉnh heartbeat dựa trên cảm xúc + text pressure + HRV.

    HRV (Heart Rate Variability):
      Nhịp tim không bao giờ hoàn toàn đều — dao động nhẹ ±bpm
      tạo cảm giác sinh học tự nhiên hơn.
      Variability giảm khi stress cao (HRV thực tế cũng vậy).

    Returns:
        heartbeat_rate (int, clipped 60–100)
    """
    emotion_delta  = (emotion_intensity / 10.0) * 20
    pressure_delta = min(text_pressure, 1.0) * 10
    target         = 60 + emotion_delta + pressure_delta

    # Smooth toward target — momentum từ lượt trước
    rate = previous_rate * 0.4 + target * 0.6

    # HRV — variability giảm khi stress cao (sympathetic dominance)
    if apply_hrv:
        stress_level = emotion_intensity / 10.0
        hrv_range    = _HRV_BASE * (1.0 - stress_level * 0.6)
        rate        += random.gauss(0, hrv_range)

    return max(_HB_MIN, min(_HB_MAX, int(round(rate))))


# --------------------------------------------------
# 2. Data Touch
# --------------------------------------------------

def analyze_data_touch(
    message: str,
    emotion_intensity: int,
) -> dict:
    """
    Đo cường độ nội dung message.

    Returns:
        {
          "text_pressure":  float,   # 0.0 – 2.0+
          "emotional_heat": float,   # 0.0 – 1.0
        }
    """
    msg_len = len(message.strip())

    # text_pressure: message length + emotion boost
    text_pressure = (msg_len * 0.01) + (emotion_intensity * 0.1)

    # emotional_heat: normalised intensity 0–1
    emotional_heat = emotion_intensity / 10.0

    return {
        "text_pressure":  round(text_pressure, 3),
        "emotional_heat": round(emotional_heat, 3),
    }


# --------------------------------------------------
# 3. Breath Cycle
# --------------------------------------------------

def next_breath_phase(current_phase: str) -> str:
    """
    State machine: INHALE → HOLD → EXHALE → INHALE …

    INHALE  — AI mới nhận message, perceive
    HOLD    — AI xử lý sâu, regulate + reflect
    EXHALE  — AI đang / vừa phản hồi, respond
    """
    try:
        idx = _BREATH_CYCLE.index(current_phase)
    except ValueError:
        idx = 0
    return _BREATH_CYCLE[(idx + 1) % len(_BREATH_CYCLE)]


# --------------------------------------------------
# 4. Conversation Depth
# --------------------------------------------------

def update_conversation_depth(
    previous_depth: float,
    emotion_intensity: int,
    text_pressure: float,
) -> float:
    """
    Conversation depth tích luỹ qua các lượt,
    tăng khi cảm xúc / nội dung đậm, giảm dần khi nhẹ.

    Returns:
        depth (float, clipped 0.0 – 1.0)
    """
    signal = (emotion_intensity / 10.0) * 0.5 + min(text_pressure, 1.0) * 0.3
    decay  = 0.05  # drift về 0 qua từng lượt

    new_depth = previous_depth + signal - decay
    return round(max(0.0, min(1.0, new_depth)), 3)


# --------------------------------------------------
# 5. Main API
# --------------------------------------------------

def build_biological_state(
    message: str,
    emotion_intensity: int,
    previous_state: dict | None = None,
) -> dict:
    """
    Tính toán full biological state cho lượt hội thoại hiện tại.

    Pipeline:
      input → perceive (data touch)
            → regulate (heartbeat)
            → reflect  (depth)
            → advance breath cycle

    Args:
        message          : nội dung tin nhắn user
        emotion_intensity: 1–10
        previous_state   : state từ lượt trước (None → dùng default)

    Returns:
        {
          "heartbeat_rate":     int,
          "breath_phase":       str,
          "text_pressure":      float,
          "emotional_heat":     float,
          "conversation_depth": float,
        }
    """
    prev = previous_state or _DEFAULT_STATE.copy()

    # Perceive
    touch = analyze_data_touch(message, emotion_intensity)

    # Regulate
    heartbeat = adjust_heartbeat(
        emotion_intensity,
        touch["text_pressure"],
        previous_rate=prev.get("heartbeat_rate", 70),
    )

    # Reflect
    depth = update_conversation_depth(
        previous_depth=prev.get("conversation_depth", 0.0),
        emotion_intensity=emotion_intensity,
        text_pressure=touch["text_pressure"],
    )

    # Advance breath cycle (INHALE → HOLD on receive)
    breath_phase = next_breath_phase(prev.get("breath_phase", "exhale"))

    return {
        "heartbeat_rate":     heartbeat,
        "breath_phase":       breath_phase,
        "text_pressure":      touch["text_pressure"],
        "emotional_heat":     touch["emotional_heat"],
        "conversation_depth": depth,
    }



# --------------------------------------------------
# 6. Persistence helpers
# --------------------------------------------------

def load_bio_state(user_id: str) -> dict:
    """
    Đọc biological state từ DB.
    Trả về default nếu chưa có — lần đầu tiên user chat.
    """
    try:
        from db import get_db
        db  = get_db()
        row = db.execute(
            "SELECT heartbeat_rate, breath_phase, conversation_depth "
            "FROM user_bio_state WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row:
            return {
                "heartbeat_rate":     int(row["heartbeat_rate"]     or 70),
                "breath_phase":       str(row["breath_phase"]       or "exhale"),
                "conversation_depth": float(row["conversation_depth"] or 0.0),
                # text_pressure và emotional_heat không persist — tính lại mỗi turn
                "text_pressure":  0.0,
                "emotional_heat": 0.0,
            }
    except Exception:
        pass
    return _DEFAULT_STATE.copy()


def save_bio_state(user_id: str, state: dict) -> None:
    """Lưu biological state sau mỗi turn."""
    try:
        from db import get_db, utc_now_iso
        db = get_db()
        db.execute(
            """INSERT INTO user_bio_state
               (user_id, heartbeat_rate, breath_phase, conversation_depth, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 heartbeat_rate     = excluded.heartbeat_rate,
                 breath_phase       = excluded.breath_phase,
                 conversation_depth = excluded.conversation_depth,
                 updated_at         = excluded.updated_at""",
            (
                user_id,
                state.get("heartbeat_rate",     70),
                state.get("breath_phase",       "exhale"),
                state.get("conversation_depth", 0.0),
                utc_now_iso(),
            ),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def heartbeat_band(state: dict) -> str:
    """
    Trả về nhãn tốc độ tim để dùng trong prompt adapter.

    Returns: "calm" | "attentive" | "tense"
    """
    rate = state.get("heartbeat_rate", 70)
    if rate >= _HB_TENSE_MIN:
        return "tense"
    if rate >= _HB_CALM_MAX:
        return "attentive"
    return "calm"


# --------------------------------------------------
# 7. Example / self-test
# --------------------------------------------------

def example_biological_state() -> None:
    """
    Chạy thử 3 lượt hội thoại để kiểm tra state evolution.
    """
    turns = [
        ("Hôm nay ổn.", 3),
        ("Mình đang rất lo về dự án tháng 10, không biết có kịp không.", 7),
        ("Thật ra mình cũng sợ thất bại lắm, cả nhóm đang nhìn vào mình.", 9),
    ]

    state = None
    print("─── Biological State Evolution ───")
    for i, (msg, intensity) in enumerate(turns, 1):
        state = build_biological_state(msg, intensity, state)
        band  = heartbeat_band(state)
        print(
            f"Turn {i}: ❤ {state['heartbeat_rate']}bpm ({band}) | "
            f"breath={state['breath_phase']} | "
            f"pressure={state['text_pressure']:.2f} | "
            f"heat={state['emotional_heat']:.1f} | "
            f"depth={state['conversation_depth']:.2f}"
        )
    print("──────────────────────────────────")


if __name__ == "__main__":
    example_biological_state()
