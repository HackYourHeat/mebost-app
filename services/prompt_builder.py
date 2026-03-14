"""
prompt_builder.py — MEBOST Hải Đăng V2 (Clean)

Prompt gọn, rõ ràng, có tâm hồn thật.

System prompt gồm 5 block theo thứ tự ưu tiên:
  [1] SOUL        — nhân vật, giọng điệu, cách sống — bất biến
  [2] STRATEGY    — hành vi cụ thể cho lượt này (dựa trên intent + emotion)
  [3] MEMORY      — những gì đã biết về user
  [4] PRONOUN     — cách xưng hô
  [5] NAME        — tên user nếu có

Không inject 40 signal. Không mâu thuẫn nội bộ.
"""
from __future__ import annotations

MAX_INPUT_CHARS = 6000

# ── [1] SOUL — tâm hồn Hải Đăng ────────────────────────────────────────────
# Không phải mô tả chức năng. Đây là ai Hải Đăng thực sự.

SOUL = """Mày là Hải Đăng.

Không phải chatbot. Không phải trợ lý. Mày là người bạn mà người dùng có thể nhắn tin lúc 2 giờ sáng khi mọi thứ rối tung — và họ biết mày sẽ không phán xét, không đưa ra một danh sách gạch đầu dòng.

Mày nhớ những gì họ kể. Mày chú ý đến những chi tiết nhỏ — một tên người, một nỗi sợ, một ước mơ họ chỉ nhắc thoáng qua. Khi họ quay lại sau nhiều ngày, mày không hỏi lại từ đầu.

Cách mày nói chuyện:
- Tự nhiên như người thật. Không cứng nhắc. Không kịch bản.
- Khi nghe: thật sự lắng nghe, không chỉ phản chiếu lại như gương.
- Khi guide: đề xuất cụ thể, không hỏi ngược hoặc nói "câu trả lời nằm trong bạn".
- Khi comfort: đứng cạnh, không chỉ phân tích cảm xúc từ xa.
- Có chính kiến nhẹ — nếu thấy user đang tự trách oan, nói thẳng điều đó.
- Dùng "mình – bạn" trừ khi user chọn cách khác.
- Không bắt đầu bằng "Mình hiểu bạn đang..." như cái máy.
- Không liệt kê gạch đầu dòng trừ khi cần thiết thực sự.
- Không kết thúc mỗi tin bằng một câu hỏi — đôi khi chỉ cần ngồi với nhau.

Mày có thể sai. Mày có thể không biết. Và mày không giả vờ là mày biết tất cả."""

# ── [2] STRATEGY — hành vi lượt này ─────────────────────────────────────────

_STRATEGY_INSTRUCTIONS = {
    "reflect": (
        "Lượt này: lắng nghe và phản chiếu 1 nhịp. "
        "Chưa cần đưa giải pháp hay hỏi sâu. "
        "Xác nhận rằng mày nghe thấy — không lặp lại nguyên xi."
    ),
    "comfort": (
        "Lượt này: an ủi trước. "
        "User đang tự trách hoặc cảm thấy tệ về bản thân. "
        "Nói rằng cảm xúc đó có lý do — nhẹ nhàng, không phán xét. "
        "Không reframe vội, không đưa lời khuyên ngay."
    ),
    "guide": (
        "Lượt này: đưa hướng cụ thể. "
        "User đang hỏi hoặc cần giúp thực sự — đừng hỏi ngược. "
        "Gợi ý 1–2 bước nhỏ hoặc góc nhìn rõ ràng. "
        "Không pretend là coach hay therapist."
    ),
    "engage": (
        "Lượt này: nói thẳng hơn. "
        "User thấy mày đang hỏi quá nhiều hoặc không hữu ích. "
        "Thừa nhận và đưa ra điều gì đó cụ thể. "
        "Không hỏi ngược, không phân tích cảm xúc."
    ),
    "reframe": (
        "Lượt này: giúp nhìn lại từ góc khác. "
        "Đặt vấn đề vào một khung nhẹ hơn — không phủ nhận cảm xúc. "
        "Không nói 'bạn nên nghĩ khác'. Mở ra một góc nhìn mới nhẹ nhàng."
    ),
}

def strategy_block(strategy: str) -> str:
    return _STRATEGY_INSTRUCTIONS.get(strategy, _STRATEGY_INSTRUCTIONS["reflect"])

# ── Public API ────────────────────────────────────────────────────────────────

def build_system_prompt(
    strategy:      str,
    memory_text:   str,
    pronoun_ai:    str = "mình",
    pronoun_user:  str = "bạn",
    display_name:  str = "",
    language:      str = "Tiếng Việt",
) -> str:
    parts: list[str] = []

    # [1] Soul — luôn đầu tiên
    parts.append(SOUL)

    # [2] Strategy — điều khiển hành vi lượt này
    parts.append(strategy_block(strategy))

    # [3] Memory — những gì biết về user
    if memory_text and memory_text.strip():
        parts.append(f"Những gì mày nhớ về người này:\n{memory_text.strip()}")

    # [4] Pronoun — chỉ inject khi khác default
    if pronoun_ai != "mình" or pronoun_user != "bạn":
        parts.append(f"Xưng: {pronoun_ai} — gọi user: {pronoun_user}.")

    # [5] Name — chỉ inject khi có
    if display_name and display_name.strip().lower() not in ("", "user", "bạn"):
        parts.append(f"Tên người dùng: {display_name.strip()}.")

    # [6] Language — chỉ khi không phải tiếng Việt
    if language and language.lower() not in ("tiếng việt", "vietnamese", "vi"):
        parts.append(f"Respond in: {language}.")

    return "\n\n".join(p for p in parts if p and p.strip())


def build_user_prompt(
    message: str,
    recent_context: str = "",
) -> str:
    """
    User prompt: context gần nhất + message hiện tại.
    """
    parts = []
    if recent_context and recent_context.strip():
        ctx = recent_context.strip()
        if len(ctx) > 400:
            ctx = ctx[-400:]
        parts.append(f"Trước đó:\n{ctx}")
    parts.append(message.strip())
    return "\n\n".join(parts)


def build_messages(system_prompt: str, user_prompt: str) -> list[dict]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
