# --------------------------------------------------
# Emotional Echo Engine — MEBOST Hải Đăng V2.0
# --------------------------------------------------
# Echo = phản chiếu cảm xúc tự nhiên trước khi AI trả lời.
# Giống reflective listening trong tham vấn — không chẩn đoán,
# không áp đặt, chỉ phản chiếu nhẹ nhàng những gì user đang mang.
#
# Output: {"echo_text": str, "echo_strength": float}
# --------------------------------------------------

from __future__ import annotations
import random

# --------------------------------------------------
# Echo phrase pools
# Mỗi emotion có 3 tầng: light / emotional / deep
# Mỗi tầng có cả VI + EN — LLM sẽ chọn ngôn ngữ phù hợp
# --------------------------------------------------

_ECHO_POOLS: dict[str, dict[str, list[str]]] = {
    "sad": {
        "light":     [
            "Có vẻ hôm nay bạn đang không được ổn lắm.",
            "Nghe có chút nặng nề trong những gì bạn chia sẻ.",
            "It sounds like today has been a difficult one.",
            "There seems to be something weighing on you.",
        ],
        "emotional": [
            "Có vẻ như có một nỗi buồn nào đó đang đi cùng bạn.",
            "Nghe như bạn đang mang một điều gì đó khá nặng.",
            "It sounds like there's a sadness you've been sitting with.",
            "It seems like something heavy has settled in.",
        ],
        "deep":      [
            "Nghe như bạn đang ở một chỗ rất khó — nơi mọi thứ cảm thấy trống và xa.",
            "Có vẻ như bạn đã mang điều này một mình từ lâu rồi.",
            "It sounds like you've been carrying this heaviness for a while now.",
            "It feels as though something deep has been weighing on you — quietly, but persistently.",
        ],
    },
    "anxious": {
        "light":     [
            "Có vẻ bạn đang có một chút lo lắng về điều này.",
            "Nghe như có điều gì đó đang tạo ra áp lực cho bạn.",
            "It sounds like something has been on your mind.",
            "There seems to be some tension around this.",
        ],
        "emotional": [
            "Nghe như sự lo lắng này đang chiếm khá nhiều không gian trong bạn.",
            "Có vẻ như bạn đang cố kiểm soát nhiều thứ cùng lúc.",
            "It sounds like the anxiety has been taking up a lot of space lately.",
            "It seems like there's a pressure building that's hard to shake.",
        ],
        "deep":      [
            "Nghe như bạn đang ở trong một vòng lặp lo lắng khá mệt — nơi bình yên cảm thấy rất xa.",
            "Có vẻ như mọi thứ đang dồn lên bạn từ nhiều hướng cùng lúc.",
            "It sounds like everything has been converging at once, and it's exhausting.",
            "It feels as though you've been bracing for something for a long time.",
        ],
    },
    "tired": {
        "light":     [
            "Nghe như bạn đang cần một chút nghỉ ngơi.",
            "Có vẻ năng lượng của bạn đang cạn dần.",
            "It sounds like you've been running on empty a bit.",
            "There seems to be a real tiredness in what you're sharing.",
        ],
        "emotional": [
            "Nghe như sự mệt mỏi này không chỉ ở thể xác — mà còn sâu hơn.",
            "Có vẻ như bạn đã cố gắng quá nhiều trong một thời gian dài.",
            "It sounds like you've been pushing through for a while now.",
            "It seems like the exhaustion goes deeper than just needing sleep.",
        ],
        "deep":      [
            "Nghe như bạn đã mang quá nhiều — đến mức không còn biết mệt là cảm giác như thế nào nữa.",
            "Có vẻ như bạn đang kiệt sức theo một cách mà khó giải thích cho người khác hiểu.",
            "It sounds like you've been depleted in a way that's hard to put into words.",
            "It feels as though you've been holding everything up for so long, you've forgotten what rest feels like.",
        ],
    },
    "angry": {
        "light":     [
            "Nghe như điều đó khiến bạn bực bội.",
            "Có vẻ như có điều gì đó không ổn đang xảy ra.",
            "It sounds like something frustrated you.",
            "There seems to be some irritation around this.",
        ],
        "emotional": [
            "Nghe như có điều gì đó thật sự không công bằng trong tình huống này.",
            "Có vẻ như sự tức giận này đến từ một chỗ rất thật.",
            "It sounds like there's a real frustration — and it makes sense.",
            "It seems like something crossed a line for you.",
        ],
        "deep":      [
            "Nghe như bạn đang tức giận — và đằng sau đó có thể là sự tổn thương.",
            "Có vẻ như điều này chạm vào một điều gì đó quan trọng với bạn.",
            "It sounds like this anger is protecting something deeper — maybe a hurt.",
            "It feels as though something important to you was dismissed or ignored.",
        ],
    },
    "happy": {
        "light":     [
            "Nghe như bạn đang có một khoảnh khắc dễ chịu.",
            "Có vẻ như có gì đó tích cực đang xảy ra với bạn.",
            "It sounds like something good has come your way.",
            "There seems to be a lightness in what you're sharing.",
        ],
        "emotional": [
            "Nghe như điều này thật sự có ý nghĩa với bạn.",
            "Có vẻ như bạn đang cảm nhận được một chút nhẹ nhõm hay niềm vui thật sự.",
            "It sounds like this genuinely matters to you.",
            "It seems like something has shifted in a good way.",
        ],
        "deep":      [
            "Nghe như đây là khoảnh khắc bạn đã chờ đợi từ lâu.",
            "Có vẻ như niềm vui này còn mang theo cả sự trân trọng.",
            "It sounds like this joy carries some relief with it too.",
            "It feels as though something you needed finally arrived.",
        ],
    },
    "neutral": {
        "light":     [
            "Mình đang lắng nghe.",
            "Bạn có muốn kể thêm không?",
            "I'm here.",
            "There may be more to what you're carrying than you've said.",
        ],
        "emotional": [
            "Nghe như có điều gì đó bạn đang cân nhắc trong lòng.",
            "Có vẻ như bạn đang ở giữa một điều gì đó.",
            "It sounds like there's something you're turning over inside.",
            "It seems like you're sitting with something.",
        ],
        "deep":      [
            "Có vẻ như điều bạn muốn nói khó nằm gọn trong một vài câu.",
            "Nghe như có nhiều lớp hơn trong những gì bạn đang cảm nhận.",
            "It sounds like what you're feeling is hard to put into words.",
            "It feels as though there's more beneath the surface.",
        ],
    },
}

_FALLBACK_ECHO = "Mình đang ở đây và lắng nghe bạn."


# --------------------------------------------------
# Core
# --------------------------------------------------

def _echo_tier(intensity: int, momentum: float) -> str:
    """light | emotional | deep — dựa trên intensity + momentum."""
    if intensity >= 8 or (intensity >= 6 and momentum >= 0.60):
        return "deep"
    if intensity >= 4 or momentum >= 0.35:
        return "emotional"
    return "light"


def _echo_strength(tier: str, trust: float) -> float:
    base = {"light": 0.25, "emotional": 0.55, "deep": 0.85}[tier]
    # Trust tăng strength nhẹ
    return round(min(1.0, base + trust * 0.10), 3)


def generate_echo(
    emotion: str,
    intensity: int,
    momentum: float,
    trust: float,
) -> dict[str, object]:
    """
    Tạo emotional echo.

    Returns:
        {"echo_text": str, "echo_strength": float}
    """
    tier  = _echo_tier(intensity, momentum)
    pool  = _ECHO_POOLS.get(emotion, _ECHO_POOLS["neutral"]).get(tier, [])
    text  = random.choice(pool) if pool else _FALLBACK_ECHO

    # Trust thấp → dùng tier nhẹ hơn để không over-interpret
    if trust < 0.40 and tier == "deep":
        lighter = _ECHO_POOLS.get(emotion, _ECHO_POOLS["neutral"]).get("emotional", [])
        text    = random.choice(lighter) if lighter else text

    return {
        "echo_text":     text,
        "echo_strength": _echo_strength(tier, trust),
    }
