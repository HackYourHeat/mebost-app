# --------------------------------------------------
# Vietnamese Pronoun Engine — MEBOST Hải Đăng V2.3
# --------------------------------------------------
# Quản lý xưng hô tiếng Việt — chọn đúng, giữ ổn định.
#
# Nguyên tắc:
#   1. Default: mình – bạn (luôn an toàn)
#   2. Inference từ message (1 lần, rồi giữ)
#   3. User có thể chọn thủ công qua API
#   4. Trust cao → có thể thân hơn nhẹ nhẹ
#   5. Không đổi giữa chừng trừ khi có tín hiệu rõ
# --------------------------------------------------

from __future__ import annotations
import re

from db import get_db, utc_now_iso

# --------------------------------------------------
# Pronoun mode definitions
# --------------------------------------------------

MODES: dict[str, dict[str, str]] = {
    "neutral_default":   {"ai": "mình",  "user": "bạn",  "label": "mình – bạn"},
    "friendly_youth":    {"ai": "tớ",    "user": "cậu",  "label": "tớ – cậu"},
    "formal_soft":       {"ai": "tôi",   "user": "bạn",  "label": "tôi – bạn"},
    "sibling_male":      {"ai": "anh",   "user": "em",   "label": "anh – em"},
    "sibling_female":    {"ai": "chị",   "user": "em",   "label": "chị – em"},
    "elder_support":     {"ai": "cô",    "user": "con",  "label": "cô – con"},
    "elder_neutral":     {"ai": "bác",   "user": "cháu", "label": "bác – cháu"},
    "elder_male":        {"ai": "chú",   "user": "cháu", "label": "chú – cháu"},
    "grandparent_male":  {"ai": "ông",   "user": "cháu", "label": "ông – cháu"},
    "grandparent_female":{"ai": "bà",    "user": "cháu", "label": "bà – cháu"},
}

_DEFAULT_MODE = "neutral_default"

# Inference patterns — thứ tự quan trọng (specific trước)
_INFER_RULES: list[tuple[list[str], str]] = [
    # pattern keywords            → mode
    (["tớ", "cậu"],               "friendly_youth"),
    (["tôi"],                     "formal_soft"),
    (["con "],                    "elder_support"),   # space sau "con" tránh nhầm "không"
    (["cháu"],                    "elder_neutral"),
    # "em" — không infer tự động (quá ambiguous)
]

# Trust threshold để allow warmer pronoun suggestion
_TRUST_WARM_THRESHOLD   = 0.65
_TRUST_FORMAL_THRESHOLD = 0.20  # trust rất thấp → quay về neutral


# --------------------------------------------------
# Migration
# --------------------------------------------------

def ensure_pronoun_table() -> None:
    """Tạo user_pronoun_profile nếu chưa có."""
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_pronoun_profile (
                user_id      TEXT PRIMARY KEY,
                pronoun_mode TEXT DEFAULT 'neutral_default',
                ai_pronoun   TEXT DEFAULT 'mình',
                user_pronoun TEXT DEFAULT 'bạn',
                source       TEXT DEFAULT 'default',
                updated_at   TEXT
            )
        """)
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Load / Save
# --------------------------------------------------

def get_pronoun_profile(user_id: str) -> dict:
    """Đọc profile. Trả về default nếu chưa có."""
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM user_pronoun_profile WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        db.close()
        if row:
            return {
                "pronoun_mode": row["pronoun_mode"] or _DEFAULT_MODE,
                "ai_pronoun":   row["ai_pronoun"]   or "mình",
                "user_pronoun": row["user_pronoun"]  or "bạn",
                "source":       row["source"]        or "default",
            }
    except Exception:
        pass
    return _mode_to_profile(_DEFAULT_MODE, "default")


def ensure_default_pronoun_profile(user_id: str) -> None:
    """Tạo row default nếu chưa có."""
    try:
        db = get_db()
        db.execute(
            """INSERT OR IGNORE INTO user_pronoun_profile
               (user_id, pronoun_mode, ai_pronoun, user_pronoun, source, updated_at)
               VALUES (?, ?, ?, ?, 'default', ?)""",
            (user_id, _DEFAULT_MODE, "mình", "bạn", utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass


def set_pronoun_mode(
    user_id: str,
    mode: str,
    source: str = "user_selected",
) -> dict:
    """Cập nhật pronoun mode. Trả về profile mới."""
    if mode not in MODES:
        mode = _DEFAULT_MODE
    profile = _mode_to_profile(mode, source)
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_pronoun_profile
               (user_id, pronoun_mode, ai_pronoun, user_pronoun, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 pronoun_mode = excluded.pronoun_mode,
                 ai_pronoun   = excluded.ai_pronoun,
                 user_pronoun = excluded.user_pronoun,
                 source       = excluded.source,
                 updated_at   = excluded.updated_at""",
            (user_id, mode,
             profile["ai_pronoun"], profile["user_pronoun"],
             source, utc_now_iso()),
        )
        db.commit()
        db.close()
    except Exception:
        pass
    return profile


# --------------------------------------------------
# Inference
# --------------------------------------------------

def infer_pronoun_mode_from_message(message: str) -> str | None:
    """
    Đọc message → đề xuất mode.
    Trả None nếu không đủ tín hiệu.
    "em" — không infer (quá ambiguous).
    """
    low = message.lower()
    for keywords, mode in _INFER_RULES:
        if any(kw in low for kw in keywords):
            return mode
    return None


# --------------------------------------------------
# Trust integration
# --------------------------------------------------

def trust_adjusted_mode(current_mode: str, trust: float) -> str:
    """
    Trust rất thấp → neutral_default (an toàn).
    Trust cao + đang ở neutral_default → gợi ý friendly_youth nhẹ hơn.
    (Không override mode đã được chọn bởi user.)
    Trả về mode cuối cùng.
    """
    if trust < _TRUST_FORMAL_THRESHOLD:
        return "neutral_default"
    if (trust >= _TRUST_WARM_THRESHOLD
            and current_mode == "neutral_default"):
        return "friendly_youth"
    return current_mode


# --------------------------------------------------
# Main resolve
# --------------------------------------------------

def resolve_pronouns(
    user_id: str,
    latest_message: str | None = None,
    trust: float = 0.30,
) -> dict:
    """
    Pipeline đầy đủ:
      load profile
      → infer from message (chỉ nếu source='default')
      → trust adjustment (chỉ nếu source='default' hoặc 'inferred')
      → save nếu có thay đổi
      → return {ai_pronoun, user_pronoun, pronoun_mode}
    """
    ensure_default_pronoun_profile(user_id)
    profile = get_pronoun_profile(user_id)
    mode    = profile["pronoun_mode"]
    source  = profile["source"]
    changed = False

    # 1. Inference — chỉ khi chưa có lựa chọn rõ ràng của user
    if latest_message and source in ("default", "inferred_from_message"):
        inferred = infer_pronoun_mode_from_message(latest_message)
        if inferred and inferred != mode:
            mode    = inferred
            source  = "inferred_from_message"
            changed = True

    # 2. Trust adjustment — chỉ nếu chưa user_selected
    if source != "user_selected":
        adjusted = trust_adjusted_mode(mode, trust)
        if adjusted != mode:
            mode    = adjusted
            source  = "inferred_from_message"
            changed = True

    # 3. Save nếu có thay đổi
    if changed:
        profile = set_pronoun_mode(user_id, mode, source)
    else:
        profile = _mode_to_profile(mode, source)

    return profile


# --------------------------------------------------
# Prompt block
# --------------------------------------------------

def pronoun_prompt_block(profile: dict) -> str:
    ai_p   = profile.get("ai_pronoun",   "mình")
    user_p = profile.get("user_pronoun", "bạn")
    return (
        f"Xưng hô trong cuộc trò chuyện này:\n"
        f"- AI xưng là: \"{ai_p}\"\n"
        f"- Gọi người dùng là: \"{user_p}\"\n"
        f"Giữ cặp xưng hô này nhất quán. Không tự ý đổi giữa chừng."
    )


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _mode_to_profile(mode: str, source: str) -> dict:
    m = MODES.get(mode, MODES[_DEFAULT_MODE])
    return {
        "pronoun_mode": mode,
        "ai_pronoun":   m["ai"],
        "user_pronoun": m["user"],
        "source":       source,
    }
