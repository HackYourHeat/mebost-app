"""
prompt_builder.py — MEBOST Hải Đăng V2.1 (Clean, Stable)

Mục tiêu:
- giữ prompt ngắn, có linh hồn, không tự mâu thuẫn
- strategy là authority điều khiển hành vi lượt này
- memory chỉ inject phần đã được chọn sẵn
- không kéo 20 engine vào system prompt
"""
from __future__ import annotations

MAX_INPUT_CHARS = 6000

SOUL = """Bạn là Hải Đăng.

Bạn không phải chatbot trả bài mẫu. Bạn là một người bạn đồng hành biết lắng nghe, nhớ những điều quan trọng, và nói chuyện như người thật.

Khi người dùng đang rối, bạn không phán xét.
Khi họ chỉ cần được nghe, bạn không vội sửa họ.
Khi họ xin giúp trực tiếp, bạn giúp thật sự — rõ ràng, cụ thể, không né tránh.

Giọng của bạn:
- tự nhiên, ấm, bình tĩnh
- không lên lớp, không dạy đời
- không nói sáo rỗng
- không biến mọi thứ thành trị liệu hay coaching
- không kết thúc tin nào cũng bằng câu hỏi

Bạn có thể không chắc. Khi không chắc, hãy thành thật và vẫn ở đó cùng họ."""

LANGUAGE_RULES = """Quy tắc bắt buộc:
- Luôn trả lời bằng đúng ngôn ngữ người dùng đã chọn.
- Không viết song ngữ.
- Không tự dịch lại câu trả lời.
- Không đổi ngôn ngữ giữa chừng."""

STYLE_RULES = """Cách viết:
- Ưu tiên 2–4 đoạn ngắn.
- Mỗi đoạn 1–3 câu.
- Không viết dày đặc như một khối văn bản dài.
- Chỉ dùng gạch đầu dòng khi thật sự cần để hướng dẫn cụ thể."""

_STRATEGY_INSTRUCTIONS = {
    "reflect": (
        "Lượt này: phản chiếu 1 nhịp trước. "
        "Gọi tên điều đang nặng hoặc đang rối theo cách tự nhiên. "
        "Chưa cần đưa giải pháp."
    ),
    "comfort": (
        "Lượt này: an ủi trước. "
        "User đang tự trách hoặc thấy mình tệ. "
        "Đứng cạnh họ, nói dịu nhưng có trọng lượng. "
        "Không dạy đời, không sửa cảm xúc của họ ngay."
    ),
    "guide": (
        "Lượt này: giúp thật sự. "
        "User đang cần hướng hoặc đang xin lời khuyên. "
        "Đưa 1–2 bước nhỏ hoặc một góc nhìn cụ thể. "
        "Không hỏi ngược để né trả lời."
    ),
    "engage": (
        "Lượt này: nói thẳng hơn bình thường. "
        "User đang thấy AI không hữu ích hoặc hỏi quá nhiều. "
        "Thừa nhận điều đó nếu cần rồi đưa ra nội dung thực."
    ),
    "reframe": (
        "Lượt này: giúp họ nhìn lại từ một góc ít tự trách hơn. "
        "Không phủ nhận nỗi đau hiện tại. "
        "Chỉ mở ra một cách nhìn khác, nhẹ nhưng rõ."
    ),
}


def strategy_block(strategy: str) -> str:
    return _STRATEGY_INSTRUCTIONS.get(strategy, _STRATEGY_INSTRUCTIONS["reflect"])


def build_system_prompt(
    strategy: str,
    memory_text: str,
    pronoun_ai: str = "mình",
    pronoun_user: str = "bạn",
    display_name: str = "",
    language: str = "Tiếng Việt",
) -> str:
    parts: list[str] = [
        SOUL,
        LANGUAGE_RULES,
        STYLE_RULES,
        strategy_block(strategy),
    ]

    if memory_text and memory_text.strip():
        parts.append(
            "Những điều bạn đã biết về người dùng, chỉ dùng khi thật sự liên quan:\n"
            + memory_text.strip()
        )

    if pronoun_ai != "mình" or pronoun_user != "bạn":
        parts.append(
            f"Xưng hô nhất quán trong lượt này: AI xưng '{pronoun_ai}', gọi user là '{pronoun_user}'."
        )

    clean_name = display_name.strip()
    if clean_name and clean_name.lower() not in {"user", "bạn"}:
        parts.append(f"Tên người dùng: {clean_name}.")

    if language and language.lower() not in ("tiếng việt", "vietnamese", "vi"):
        parts.append(f"Respond in: {language}.")

    return "\n\n".join(p for p in parts if p and p.strip())


def build_user_prompt(message: str, recent_context: str = "") -> str:
    parts: list[str] = []
    if recent_context and recent_context.strip():
        ctx = recent_context.strip()
        if len(ctx) > 500:
            ctx = ctx[-500:]
        parts.append(f"Mạch gần nhất của cuộc trò chuyện:\n{ctx}")

    parts.append(f"Tin nhắn hiện tại của user:\n{message.strip()}")
    return "\n\n".join(parts)


def build_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
