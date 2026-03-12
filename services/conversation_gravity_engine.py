# --------------------------------------------------
# Conversation Gravity Engine — MEBOST Hải Đăng V1.9
# --------------------------------------------------
# Gravity = lực kéo tự nhiên giúp cuộc trò chuyện tiếp tục.
# Không thao túng — chỉ cải thiện flow phản hồi.
#
# Gravity score = f(momentum, trust, emotion_intensity)
# Gravity hint  → gợi ý 1 continuation hook cho prompt
# --------------------------------------------------

from __future__ import annotations
import random

# --------------------------------------------------
# Hook pools — 3 loại, mỗi loại có tiếng Việt + English
# --------------------------------------------------

_HOOKS_REFLECTION = [
    "Nghe có vẻ điều này đã đè nặng lên bạn một thời gian rồi.",
    "Mình cảm nhận được có điều gì đó thật sự quan trọng ẩn sau những gì bạn chia sẻ.",
    "Điều bạn mô tả nghe có vẻ không hề nhẹ nhàng chút nào.",
    "It sounds like this has been weighing on you for a while.",
    "There seems to be something deeper underneath what you're sharing.",
]

_HOOKS_CURIOSITY = [
    "Phần nào trong đó cảm thấy nặng nề nhất với bạn lúc này?",
    "Điều gì khiến bạn khó gạt bỏ nhất?",
    "Khi bạn nghĩ về điều này, cảm giác đầu tiên xuất hiện là gì?",
    "What part of that feels hardest right now?",
    "When you sit with this, what comes up first?",
]

_HOOKS_OPEN_THREAD = [
    "Mình tò mò điều đó đã diễn ra như thế nào với bạn.",
    "Bạn có muốn kể thêm về khoảng thời gian đó không?",
    "Mình đang lắng nghe — bạn có muốn tiếp tục không?",
    "I'm curious how that unfolded for you.",
    "I'd love to hear more about that time, if you want to share.",
]

_HOOK_POOLS = {
    "reflection":   _HOOKS_REFLECTION,
    "curiosity":    _HOOKS_CURIOSITY,
    "open_thread":  _HOOKS_OPEN_THREAD,
}

# --------------------------------------------------
# Score
# --------------------------------------------------

def compute_gravity(
    momentum: float,
    trust: float,
    emotion_intensity: int,
) -> float:
    """
    gravity = momentum*0.4 + trust*0.3 + (emotion/10)*0.3
    Clamp [0.0, 1.0]
    """
    score = (
        momentum * 0.40
        + trust   * 0.30
        + (emotion_intensity / 10.0) * 0.30
    )
    return round(min(1.0, max(0.0, score)), 3)


# --------------------------------------------------
# Hook selection
# --------------------------------------------------

def select_hook(gravity: float, intent: str = "vent") -> str | None:
    """
    Chọn 1 continuation hook phù hợp với gravity + intent.
    Trả None nếu gravity thấp — không ép continuation.

    Low  (<0.30) → None
    Mid  (0.30–0.60) → reflection hoặc open_thread
    High (>0.60) → curiosity hoặc reflection
    """
    if gravity < 0.30:
        return None

    if gravity >= 0.60:
        pool_key = random.choice(["curiosity", "reflection"])
    else:
        pool_key = random.choice(["reflection", "open_thread"])

    # Intent override: casual → lighter hooks
    if intent == "casual" and gravity < 0.55:
        pool_key = "open_thread"

    pool = _HOOK_POOLS[pool_key]
    return random.choice(pool)


# --------------------------------------------------
# Prompt hint
# --------------------------------------------------

def gravity_prompt_hint(gravity: float, hook: str | None) -> str:
    """
    Trả về đoạn hướng dẫn ngắn cho prompt.
    Nếu có hook → đề xuất thêm vào cuối reply.
    """
    if gravity < 0.30:
        return (
            "Gravity thấp — giữ reply đơn giản, "
            "không cần đặt câu hỏi hoặc mời tiếp tục."
        )

    lines = []
    if gravity >= 0.60:
        lines.append(
            "Gravity cao — có thể dùng câu hỏi phản chiếu sâu "
            "hoặc mời user kể tiếp."
        )
    else:
        lines.append(
            "Gravity trung bình — phản chiếu nhẹ "
            "hoặc câu hỏi mở ngắn."
        )

    if hook:
        lines.append(f'Gợi ý continuation hook (dùng hoặc không tuỳ ngữ cảnh): "{hook}"')

    return " ".join(lines)
