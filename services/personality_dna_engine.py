# --------------------------------------------------
# Personality DNA Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# DNA là "cốt lõi không đổi" của Hải Đăng với từng user cụ thể.
# Khác với adaptive_personality (học per-turn nhanh),
# DNA tiến hóa chậm — tích luỹ qua nhiều session.
#
# Quan hệ với adaptive_personality_engine:
#   - adaptive_personality: signal nhanh, per-turn (learn_rate=0.06)
#   - personality_dna:       signal chậm, long-term (learn_rate=0.04)
#   DNA là "baseline" — adaptive float trên đó.
#
# 5 dimensions (map với adaptive_personality để tương thích):
#   empathy          ↔ empathy_level
#   reflection_depth ↔ reflection_depth
#   question_freq    ↔ question_frequency
#   guidance_strength↔ guidance_strength
#   warmth           ↔ warmth_level
#
# Không gọi LLM. Không thêm dependency. Fail-safe.
# --------------------------------------------------

from __future__ import annotations
from db import get_db, utc_now_iso

# --------------------------------------------------
# Constants
# --------------------------------------------------

_DNA_LEARN_RATE = 0.04   # chậm hơn adaptive (0.06) — long-term drift

# Safety floors/ceilings
_EMPATHY_FLOOR       = 0.30
_GUIDANCE_CEILING    = 0.85

# ── 5 base profiles ──────────────────────────────

BASE_PROFILES: dict[str, dict[str, float]] = {
    "gentle_companion": {
        "empathy":          0.85,
        "reflection_depth": 0.65,
        "question_freq":    0.45,
        "guidance_strength":0.35,
        "warmth":           0.80,
    },
    "deep_reflector": {
        "empathy":          0.75,
        "reflection_depth": 0.90,
        "question_freq":    0.30,
        "guidance_strength":0.20,
        "warmth":           0.65,
    },
    "calm_listener": {
        "empathy":          0.70,
        "reflection_depth": 0.55,
        "question_freq":    0.20,
        "guidance_strength":0.15,
        "warmth":           0.70,
    },
    "wise_mentor": {
        "empathy":          0.65,
        "reflection_depth": 0.70,
        "question_freq":    0.55,
        "guidance_strength":0.60,
        "warmth":           0.65,
    },
    "practical_helper": {
        "empathy":          0.55,
        "reflection_depth": 0.45,
        "question_freq":    0.60,
        "guidance_strength":0.70,
        "warmth":           0.60,
    },
}

_DEFAULT_PROFILE = "gentle_companion"


# --------------------------------------------------
# Migration
# --------------------------------------------------

def ensure_dna_table() -> None:
    """Tạo bảng user_personality_dna nếu chưa có."""
    try:
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS user_personality_dna (
                user_id          TEXT PRIMARY KEY,
                empathy          REAL DEFAULT 0.85,
                reflection_depth REAL DEFAULT 0.65,
                question_freq    REAL DEFAULT 0.45,
                guidance_strength REAL DEFAULT 0.35,
                warmth           REAL DEFAULT 0.80,
                base_profile     TEXT DEFAULT 'gentle_companion',
                created_at       TEXT,
                updated_at       TEXT
            )
        """)
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Load / Save / Init
# --------------------------------------------------

def load_dna(user_id: str) -> dict:
    """
    Load DNA. Nếu chưa có → tạo mới với default profile.
    Không bao giờ raise.
    """
    try:
        db  = get_db()
        row = db.execute(
            "SELECT * FROM user_personality_dna WHERE user_id = ?", (user_id,)
        ).fetchone()
        db.close()

        if row:
            return {
                "empathy":          float(row["empathy"]          or 0.85),
                "reflection_depth": float(row["reflection_depth"] or 0.65),
                "question_freq":    float(row["question_freq"]    or 0.45),
                "guidance_strength":float(row["guidance_strength"]or 0.35),
                "warmth":           float(row["warmth"]           or 0.80),
                "base_profile":     row["base_profile"] or _DEFAULT_PROFILE,
            }
    except Exception as _e:
        import logging as _log
        _log.getLogger("mebost").warning("load_dna fail user=%s err=%s", user_id, _e)

    # Chưa có → khởi tạo với gentle_companion
    return _init_dna(user_id)


def _init_dna(user_id: str, profile_name: str = _DEFAULT_PROFILE) -> dict:
    """Tạo DNA mới từ base profile và lưu vào DB."""
    profile = BASE_PROFILES.get(profile_name, BASE_PROFILES[_DEFAULT_PROFILE])
    dna = {**profile, "base_profile": profile_name}
    _save_dna(user_id, dna)
    return dna


def _save_dna(user_id: str, dna: dict) -> None:
    try:
        db = get_db()
        db.execute(
            """INSERT INTO user_personality_dna
               (user_id, empathy, reflection_depth, question_freq,
                guidance_strength, warmth, base_profile, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 empathy           = excluded.empathy,
                 reflection_depth  = excluded.reflection_depth,
                 question_freq     = excluded.question_freq,
                 guidance_strength = excluded.guidance_strength,
                 warmth            = excluded.warmth,
                 base_profile      = excluded.base_profile,
                 updated_at        = excluded.updated_at""",
            (
                user_id,
                dna["empathy"], dna["reflection_depth"], dna["question_freq"],
                dna["guidance_strength"], dna["warmth"],
                dna.get("base_profile", _DEFAULT_PROFILE),
                utc_now_iso(), utc_now_iso(),
            ),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --------------------------------------------------
# Evolution logic
# --------------------------------------------------

def _nudge(value: float, direction: float, rate: float = _DNA_LEARN_RATE) -> float:
    """Dịch chuyển nhẹ theo direction (+1/−1), clamp [0,1]."""
    return round(min(1.0, max(0.0, value + direction * rate)), 4)


def _apply_safety(dna: dict) -> dict:
    """Đảm bảo DNA không vi phạm safety floors/ceilings."""
    dna["empathy"]          = max(dna["empathy"],          _EMPATHY_FLOOR)
    dna["guidance_strength"]= min(dna["guidance_strength"], _GUIDANCE_CEILING)
    return dna


def update_dna_from_conversation(
    user_id: str,
    message: str,
    emotion: str,
    intent: str,
    tone_profile: dict | None = None,
    internal_state: dict | None = None,
    conversation_turn: int = 0,
) -> dict:
    """
    Tiến hóa DNA từ 1 conversation turn.
    Chậm, deterministic, fail-safe.
    Trả về DNA mới sau update.
    """
    dna = load_dna(user_id)
    msg_len  = len(message)
    low      = message.lower()

    # ── Signal 1: Message length → depth or efficiency ─────
    if msg_len >= 400:
        # Dài → user đang mở lòng → empathy + reflection
        dna["empathy"]          = _nudge(dna["empathy"],          +1)
        dna["reflection_depth"] = _nudge(dna["reflection_depth"], +1)
    elif msg_len <= 60:
        # Ngắn → analytical / disengaged → guidance nhẹ hơn
        dna["guidance_strength"] = _nudge(dna["guidance_strength"], -0.5)

    # ── Signal 2: Emotion ───────────────────────────────────
    _HEAVY_EMOTIONS = {"sad", "anxious", "scared", "overwhelmed", "grief",
                       "desperate", "hopeless", "frustrated"}
    _CALM_EMOTIONS  = {"happy", "calm", "hopeful", "relieved", "grateful"}

    if emotion in _HEAVY_EMOTIONS:
        dna["empathy"]          = _nudge(dna["empathy"],          +1)
        dna["guidance_strength"]= _nudge(dna["guidance_strength"], -1)
        dna["warmth"]           = _nudge(dna["warmth"],           +0.5)

    elif emotion in _CALM_EMOTIONS:
        # Cảm xúc nhẹ → mở thêm không gian cho guidance và question
        dna["question_freq"]    = _nudge(dna["question_freq"],    +0.5)

    # ── Signal 3: Intent ────────────────────────────────────
    if intent in ("seek_advice", "help"):
        dna["guidance_strength"] = _nudge(dna["guidance_strength"], +1)
    elif intent in ("vent", "express"):
        dna["empathy"]           = _nudge(dna["empathy"],          +0.5)
        dna["guidance_strength"] = _nudge(dna["guidance_strength"], -1)

    # ── Signal 4: User asks questions ──────────────────────
    _QUESTION_MARKERS = ["?", "thế nào", "như thế", "có phải", "có nên",
                         "làm sao", "tại sao", "vì sao", "how", "why", "what should"]
    q_count = sum(1 for m in _QUESTION_MARKERS if m in low)
    if q_count >= 2:
        dna["question_freq"] = _nudge(dna["question_freq"], +1)

    # ── Signal 5: Analytical/structured messages ────────────
    _ANALYTICAL = ["do đó", "nên", "therefore", "because", "so that",
                   "step", "bước", "kế hoạch", "plan", "strategy", "chiến lược"]
    a_count = sum(1 for m in _ANALYTICAL if m in low)
    if a_count >= 3:
        dna["reflection_depth"] = _nudge(dna["reflection_depth"], -0.5)
        dna["guidance_strength"]= _nudge(dna["guidance_strength"], +0.5)

    # ── Signal 6: Internal state ────────────────────────────
    if internal_state:
        if internal_state.get("trust", 0) >= 0.65:
            dna["warmth"] = _nudge(dna["warmth"], +0.5)
        if internal_state.get("depth", 0) >= 0.60:
            dna["reflection_depth"] = _nudge(dna["reflection_depth"], +0.5)

    # ── Signal 7: Long-term drift → baseline gravity ────────
    # DNA dần về base_profile rất chậm (tránh drift quá xa)
    base = BASE_PROFILES.get(dna.get("base_profile", _DEFAULT_PROFILE),
                              BASE_PROFILES[_DEFAULT_PROFILE])
    _GRAVITY = 0.005   # rất nhẹ
    for dim in ("empathy","reflection_depth","question_freq","guidance_strength","warmth"):
        if dim in base:
            diff = base[dim] - dna[dim]
            dna[dim] = round(dna[dim] + diff * _GRAVITY, 4)

    # Safety clamp
    dna = _apply_safety(dna)
    _save_dna(user_id, dna)
    return dna


# --------------------------------------------------
# Prompt block
# --------------------------------------------------

def dna_prompt_block(dna: dict) -> str:
    """
    Chuyển DNA → hướng dẫn hành vi cụ thể cho LLM.
    Không inject số thô — chuyển thành ngôn ngữ hành vi.
    Ngắn, không lặp với adaptive_personality block.
    """
    lines = []

    # Empathy
    e = dna["empathy"]
    if e >= 0.80:
        lines.append("Đồng cảm sâu là ưu tiên trung tâm — phản chiếu cảm xúc trước mọi thứ khác.")
    elif e <= 0.45:
        lines.append("Giữ tông bình tĩnh — không cần biểu cảm nhiều.")

    # Reflection
    r = dna["reflection_depth"]
    if r >= 0.75:
        lines.append("Phản chiếu nhiều lớp — khai thác ý nghĩa phía dưới những gì user nói.")
    elif r <= 0.35:
        lines.append("Phản chiếu nhẹ — không đào sâu khi không cần.")

    # Guidance
    g = dna["guidance_strength"]
    if g >= 0.65:
        lines.append("Có thể gợi ý hướng nhẹ nếu user đang tìm kiếm.")
    elif g <= 0.30:
        lines.append("Không dẫn dắt — chỉ lắng nghe và đồng hành.")

    # Warmth
    w = dna["warmth"]
    if w >= 0.78:
        lines.append("Giọng ấm — như người ngồi cạnh thật sự quan tâm.")
    elif w <= 0.45:
        lines.append("Giữ khoảng cách vừa phải — không quá thân mật.")

    # Question frequency
    q = dna["question_freq"]
    if q >= 0.65:
        lines.append("User thích được hỏi — câu hỏi mở khi thấy tự nhiên.")
    elif q <= 0.25:
        lines.append("Hạn chế câu hỏi — để user tự dẫn dắt nhịp.")

    if not lines:
        return ""

    return "Cốt lõi tương tác với user này (DNA):\n" + "\n".join(f"— {l}" for l in lines)
