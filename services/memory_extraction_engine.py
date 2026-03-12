# --------------------------------------------------
# Memory Extraction Engine — MEBOST Hải Đăng V1.1
# --------------------------------------------------
# Tách biệt hoàn toàn việc:
#   RAW message → candidate memory node
#
# Không save DB ở đây.
# Chỉ quyết định: có đáng nhớ không? nhớ gì? nhớ kiểu gì?
# --------------------------------------------------

from __future__ import annotations

import re

# --------------------------------------------------
# Constants
# --------------------------------------------------

MIN_MESSAGE_LENGTH = 15          # bỏ qua message quá ngắn (trừ khi có strong signal)
MAX_MEMORY_TEXT    = 200         # ký tự tối đa mỗi memory node

EXTRACT_THRESHOLD  = 6           # importance_score tối thiểu để extract

# --------------------------------------------------
# FIX 1 — Short message nhưng có strong memory signal
# Những pattern này bypass MIN_MESSAGE_LENGTH
# Ví dụ: "Tên mình là T", "Mình sợ chết", "Đừng gọi mình là em"
# --------------------------------------------------

_STRONG_SIGNAL_PATTERNS: list[str] = [
    r"tên (mình|tôi|tao)\s+(là|=)",        # identity: tên mình là X
    r"gọi (mình|tôi|tao)\s+là",            # identity: gọi mình là X
    r"my name is",
    r"call me",
    r"mình sợ",                             # fear signal
    r"tôi sợ",
    r"i'?m afraid",
    r"i fear",
    r"đừng (gọi|nói|hỏi|nhắc)",            # boundary
    r"please don'?t",
    r"tôi không muốn",
    r"mình không muốn.*nhắc",
]

_STRONG_SIGNAL_COMPILED = [re.compile(p, re.I) for p in _STRONG_SIGNAL_PATTERNS]

# --------------------------------------------------
# Noise filter — những message không đáng nhớ
# --------------------------------------------------

_NOISE_PATTERNS: list[str] = [
    r"^ok[\s!.]*$",
    r"^haha[\s!.]*$",
    r"^hi[\s!.]*$",
    r"^hello[\s!.]*$",
    r"^chào[\s!.]*$",
    r"^xin chào[\s!.]*$",
    r"^test[\s!.]*$",
    r"^cảm ơn[\s!.]*$",
    r"^thanks?[\s!.]*$",
    r"^thx[\s!.]*$",
    r"^okay[\s!.]*$",
    r"^ừ[\s!.]*$",
    r"^uh[\s!.]*$",
    r"^vâng[\s!.]*$",
    r"^đúng[\s!.]*$",
    r"^yeah[\s!.]*$",
    r"^yes[\s!.]*$",
    r"^no[\s!.]*$",
    r"^không[\s!.]*$",
    r"^k[\s!.]*$",
    r"^dc[\s!.]*$",
    r"^được[\s!.]*$",
    r"^👍+$",
    r"^😊+$",
]

_NOISE_COMPILED = [re.compile(p, re.I) for p in _NOISE_PATTERNS]

# --------------------------------------------------
# Memory type rules — từ khóa → type
# (chi tiết hơn memory_engine._TYPE_RULES)
# --------------------------------------------------

_TYPE_RULES: list[tuple[list[str], str]] = [
    (["tên mình là", "my name is", "gọi mình là", "call me",
      "mình tên", "tôi tên"],                                   "identity"),
    (["thích", "prefer", "yêu thích", "không thích",
      "do not like", "dislike", "ghét"],                        "preference"),
    (["mục tiêu", "goal", "muốn build", "want to build",
      "muốn trở thành", "want to become", "ước mơ", "dream",
      "kế hoạch", "plan"],                                      "goal"),
    (["người yêu", "bạn gái", "bạn trai", "vợ", "chồng",
      "relationship", "bạn thân", "partner", "gia đình",
      "family", "anh", "chị", "em", "bố", "mẹ"],               "relationship"),
    (["lo", "sợ", "anxious", "worried", "mệt", "buồn",
      "tức", "angry", "cô đơn", "alone", "overwhelmed",
      "căng thẳng", "stress", "nặng lòng"],                     "emotional_pattern"),
    (["đừng", "không thích bị", "boundary", "please don't",
      "tôi không muốn"],                                        "boundary"),
    (["đang làm", "công việc", "nghề", "career", "job",
      "thất nghiệp", "unemployed", "học", "student",
      "trường", "school", "dự án", "project"],                  "life_context"),
]

_FALLBACK_TYPE = "life_context"

# --------------------------------------------------
# Compression rules
# Memory text phải ngắn gọn — không lưu nguyên câu dài
# --------------------------------------------------

_COMPRESSION_PREFIXES = [
    "mình ", "tôi ", "i ", "bạn ", "mình đang ", "tôi đang ",
    "mình đã ", "tôi đã ", "mình sẽ ", "tôi sẽ ",
    "hiện tại mình ", "hiện tại tôi ",
]


# --------------------------------------------------
# FIX 2 — Emotional core keywords
# Nếu câu chứa những từ này, _compress_text giữ nguyên
# thay vì cắt tại câu đầu tiên
# --------------------------------------------------

_EMOTIONAL_CORE_KEYWORDS = [
    "sợ", "fear", "lo", "mất", "đổ bể", "thất bại", "chết",
    "không còn", "không ai", "cô đơn", "alone", "overwhelmed",
    "nặng lòng", "kiệt sức", "burnout", "vỡ", "tan",
]


def _compress_text(text: str) -> str:
    """
    Rút ngắn text thành memory node ngắn gọn.
    Mục tiêu: 60–200 ký tự, rõ nghĩa, dạng "Người dùng X".

    FIX: Nếu câu chứa emotional core keywords (sợ, lo, đổ bể, ...),
    không cắt tại câu đầu tiên — giữ nguyên để bảo toàn sắc thái cảm xúc.
    """
    text = text.strip()

    # Kiểm tra emotional core trước khi cắt câu
    low = text.lower()
    has_emotional_core = any(kw in low for kw in _EMOTIONAL_CORE_KEYWORDS)

    if not has_emotional_core:
        # An toàn để cắt tại câu đầu tiên
        first_sentence = re.split(r"[.!?…\n]", text)[0].strip()
        if len(first_sentence) >= 20:
            text = first_sentence

    # Viết lại dạng "Người dùng ..."
    low = text.lower()
    for prefix in _COMPRESSION_PREFIXES:
        if low.startswith(prefix):
            rest = text[len(prefix):].strip()
            if rest:
                text = rest[0].upper() + rest[1:]
            break

    # Prefix chuẩn
    if not text.lower().startswith("người dùng"):
        text = "Người dùng " + text[0].lower() + text[1:]

    return text[:MAX_MEMORY_TEXT]


# --------------------------------------------------
# Public API
# --------------------------------------------------

def _has_strong_signal(text: str) -> bool:
    """
    Trả về True nếu message ngắn nhưng chứa strong memory signal.
    Bypass MIN_MESSAGE_LENGTH để tránh mất ký ức quan trọng.

    Ví dụ: "Tên mình là T.", "Mình sợ chết.", "Đừng gọi mình là em."
    """
    for pattern in _STRONG_SIGNAL_COMPILED:
        if pattern.search(text):
            return True
    return False


def is_noise(message: str) -> bool:
    """
    Trả về True nếu message không đáng nhớ.

    Logic:
    - Nếu có strong signal → KHÔNG phải noise dù ngắn
    - Nếu quá ngắn và không có strong signal → noise
    - Nếu match noise pattern → noise
    """
    stripped = message.strip()

    # Strong signal override — bypass length filter
    if _has_strong_signal(stripped):
        return False

    if len(stripped) < MIN_MESSAGE_LENGTH:
        return True

    for pattern in _NOISE_COMPILED:
        if pattern.match(stripped):
            return True

    return False


def classify_memory_type(text: str) -> str:
    """
    Phân loại memory type dựa trên keyword matching.
    """
    lower = text.lower()
    for keywords, memory_type in _TYPE_RULES:
        if any(kw in lower for kw in keywords):
            return memory_type
    return _FALLBACK_TYPE


def build_memory_candidate(
    text: str,
    emotion_intensity: int,
    importance_score: int,
) -> dict | None:
    """
    Từ raw message text, quyết định và tạo memory candidate.

    Args:
        text              : raw message text từ user
        emotion_intensity : 1–10
        importance_score  : 1–10 từ importance_engine

    Returns:
        dict với keys: memory_type, memory_text, importance_score
        None nếu không đủ điều kiện extract
    """
    # Filter noise
    if is_noise(text):
        return None

    # Threshold check — tăng nhẹ nếu emotion thấp
    effective_threshold = EXTRACT_THRESHOLD
    if emotion_intensity <= 3:
        effective_threshold = EXTRACT_THRESHOLD + 1

    if importance_score < effective_threshold:
        return None

    memory_type = classify_memory_type(text)
    memory_text = _compress_text(text)

    if not memory_text or len(memory_text) < 10:
        return None

    return {
        "memory_type":    memory_type,
        "memory_text":    memory_text,
        "importance_score": importance_score,
    }


# --------------------------------------------------
# Self-test
# --------------------------------------------------

def test_memory_extraction() -> None:
    """
    Test extraction pipeline — 5 nhóm edge cases.
    """
    cases = [
        # ── Noise ──────────────────────────────────────────────────────
        ("ok",                                        2, 8, False, "noise"),
        ("haha",                                      3, 9, False, "noise"),
        ("Cảm ơn bạn",                                2, 7, False, "noise"),
        ("test",                                      1, 9, False, "noise"),

        # ── Normal extraction ──────────────────────────────────────────
        ("Mình đang rất lo về deadline tháng 10.",    7, 8, True,  "normal"),
        ("Mình ước mơ xây một AI thật sự đồng hành.", 6, 9, True,  "normal"),
        ("Mình không thích bị khuyên quá nhiều.",     5, 7, True,  "normal"),

        # ── FIX 1: Short nhưng strong signal — PHẢI extract ───────────
        ("Tên mình là T.",                            4, 8, True,  "fix1-short+strong"),
        ("Đừng gọi mình là em.",                      5, 7, True,  "fix1-short+strong"),
        ("Mình sợ chết.",                             8, 9, True,  "fix1-short+strong"),

        # ── FIX 2: Emotional core phải còn trong memory_text ──────────
        ("Mình đang lo về deadline tháng 10 vì sợ mọi thứ đổ bể.", 7, 8, True, "fix2-emotional"),

        # ── Below threshold ────────────────────────────────────────────
        ("Lo lắm.",                                   7, 5, False, "threshold"),
    ]

    print("─── Memory Extraction Engine — Edge Case Tests ───")
    all_ok = True
    for msg, ei, imp, expect, label in cases:
        candidate = build_memory_candidate(msg, ei, imp)
        got    = candidate is not None
        ok     = got == expect
        status = "OK  " if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"  {status}  [{label:22}]  {msg[:52]}")
        if candidate:
            mt = candidate["memory_text"]
            # FIX 2 check: emotional core phải còn trong text
            if label == "fix2-emotional":
                has_core = any(kw in mt for kw in ["sợ", "đổ bể", "lo"])
                core_ok  = "✓ core giữ" if has_core else "✗ core MẤT"
                print(f"         {core_ok}  →  {mt[:80]}")
            else:
                print(f"         type={candidate['memory_type']:16} {mt[:60]}")

    print()
    print("ALL OK" if all_ok else "ISSUES FOUND")
    print("──────────────────────────────────────────────────")


if __name__ == "__main__":
    test_memory_extraction()
