# --------------------------------------------------
# Response Strategy Engine — MEBOST Hải Đăng V1.0
# --------------------------------------------------
# Chọn loại phản hồi cho từng lượt.
# Deterministic rule-based — không gọi LLM.
#
# 5 strategies:
#   reflect   — phản chiếu cảm xúc (1–2 nhịp tối đa)
#   comfort   — an ủi, xác nhận giá trị
#   engage    — nói thẳng hơn, không hỏi ngược
#   guide     — đưa góc nhìn / bước nhỏ / hướng nghĩ
#   reframe   — giúp nhìn tình huống từ góc khác
#
# Logic ưu tiên:
#   1. Frustration với AI (bạn cứ hỏi…)  → engage
#   2. Self-attack mạnh (tôi vô dụng)    → comfort / reframe
#   3. Xin lời khuyên trực tiếp          → guide
#   4. Stuck / rối / không biết làm gì   → guide
#   5. Cảm xúc nặng, chưa xin giúp      → reflect (max 1–2 lần)
#   6. Default                           → reflect
# --------------------------------------------------

from __future__ import annotations
import re

STRATEGIES = ["reflect", "comfort", "engage", "guide", "reframe"]

# Frustration với AI — phải chuyển sang engage
_FRUSTRATION_PATTERNS = [
    "bạn cứ hỏi", "bạn không giúp", "tại sao bạn im",
    "bạn không trả lời", "cứ hỏi ngược", "không giúp gì",
    "just answer", "stop asking", "you keep asking",
    "you're not helping", "why won't you",
]

# Self-attack — cần comfort/reframe
_SELF_ATTACK_PATTERNS = [
    "vô dụng", "ăn bám", "thất bại rồi", "không xứng",
    "tôi vô dụng", "mình vô dụng", "tôi thật tệ", "mình thật tệ",
    "tôi không xứng", "mình không xứng", "tôi thất bại",
    "tôi không làm được", "mình không làm được",
    "i'm worthless", "i'm useless", "i'm a failure",
    "i hate myself", "i'm so stupid",
]

# Stuck / rối — cần guide
_STUCK_PATTERNS = [
    "không biết phải làm gì", "không biết làm sao",
    "mình đang rối", "tôi đang rối", "tôi bị stuck",
    "i don't know what to do", "i'm lost", "i'm stuck",
    "không có hướng", "không biết bắt đầu từ đâu",
]


def select_strategy(
    message:    str,
    intent:     str,
    emotion:    str,
    policy:     dict | None = None,
    mirror_mode: str = "deep_mirror",
) -> str:
    """
    Trả về strategy string cho lượt này.
    Fail-safe: luôn trả về một trong STRATEGIES.
    """
    try:
        return _select(message, intent, emotion, policy or {}, mirror_mode)
    except Exception:
        return "reflect"


def strategy_instruction(strategy: str, advice_allowed: bool = False) -> str:
    """
    Tạo instruction ngắn gọn inject vào prompt.
    ~15–30 tokens.
    """
    _INSTRUCTIONS = {
        "reflect": (
            "Lượt này: phản chiếu 1 nhịp. "
            "Không hỏi ngược ngay. Không đưa giải pháp trừ khi user dẫn đến đó."
        ),
        "comfort": (
            "Lượt này: an ủi trước. "
            "Xác nhận cảm xúc, không phán xét, không reframe vội. "
            "Nếu user đang tự trách, nói nhẹ rằng điều đó không hoàn toàn đúng."
        ),
        "engage": (
            "Lượt này: nói thẳng hơn. "
            "User đang muốn được nghe — đừng hỏi ngược. "
            "Thừa nhận nếu đã hỏi quá nhiều. Đưa ra điều gì đó cụ thể."
        ),
        "guide": (
            "Lượt này: đưa hướng. "
            "User đang xin giúp — hãy gợi ý 1–2 bước nhỏ hoặc góc nhìn cụ thể. "
            "Giọng vẫn nhẹ, không áp đặt, nhưng phải có nội dung thực."
        ),
        "reframe": (
            "Lượt này: giúp nhìn lại. "
            "Đặt vấn đề user đang gặp vào một góc nhìn khác nhẹ nhàng hơn. "
            "Không mâu thuẫn thẳng, nhưng mở ra cách nghĩ ít tự trách hơn."
        ),
    }
    base = _INSTRUCTIONS.get(strategy, _INSTRUCTIONS["reflect"])
    if strategy in ("guide", "engage") and not advice_allowed:
        # Đảm bảo policy không block lời khuyên khi strategy yêu cầu
        base += " [advice_allowed override: strategy requires it]"
    return base


# --------------------------------------------------
# Core logic
# --------------------------------------------------

def _select(
    message: str,
    intent:  str,
    emotion: str,
    policy:  dict,
    mirror_mode: str,
) -> str:
    msg_lower = message.lower()

    # Priority 1: Frustration với AI → engage
    if any(p in msg_lower for p in _FRUSTRATION_PATTERNS):
        return "engage"

    # Priority 2: Self-attack → comfort hoặc reframe
    if any(p in msg_lower for p in _SELF_ATTACK_PATTERNS):
        # Nếu nặng (nhiều từ tự trách) → comfort, nhẹ hơn → reframe
        hit_count = sum(1 for p in _SELF_ATTACK_PATTERNS if p in msg_lower)
        return "comfort" if hit_count >= 2 else "reframe"

    # Priority 3: Intent help → guide
    if intent == "help" or policy.get("advice_allowed"):
        return "guide"

    # Priority 4: Stuck → guide
    if any(p in msg_lower for p in _STUCK_PATTERNS):
        return "guide"

    # Priority 5: Cảm xúc nặng, chưa xin giúp → reflect
    # (mirror mode silent_presence cũng map về reflect)
    if mirror_mode == "silent_presence":
        return "comfort"

    return "reflect"
