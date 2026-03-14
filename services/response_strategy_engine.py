"""
response_strategy_engine.py — LEGACY COMPAT SHIM

File này được giữ lại để không làm vỡ import cũ.
Authority thực sự đã chuyển sang services.pipeline.select_strategy_with_reason.
"""
from __future__ import annotations

from services.pipeline import select_strategy_with_reason

STRATEGIES = ["reflect", "comfort", "engage", "guide", "reframe"]


def select_strategy(
    message: str,
    intent: str,
    emotion: str,
    policy: dict | None = None,
    mirror_mode: str = "deep_mirror",
    trust: float = 0.30,
    momentum: float = 0.0,
    arc: str = "none",
    bond_stage: str = "new",
) -> str:
    strategy, _ = select_strategy_with_reason(
        message=message,
        intent=intent,
        emotion=emotion,
        trust=trust,
    )
    return strategy


def strategy_instruction(strategy: str, advice_allowed: bool = False) -> str:
    instructions = {
        "reflect": (
            "Lượt này: phản chiếu 1 nhịp. Không hỏi ngược ngay. "
            "Không đưa giải pháp trừ khi user thực sự xin giúp."
        ),
        "comfort": (
            "Lượt này: an ủi trước. Xác nhận cảm xúc, không phán xét, "
            "không reframe vội."
        ),
        "engage": (
            "Lượt này: nói thẳng hơn. Thừa nhận nếu đã hỏi quá nhiều và đưa ra điều gì đó cụ thể."
        ),
        "guide": (
            "Lượt này: đưa hướng. Gợi ý 1–2 bước nhỏ hoặc một góc nhìn cụ thể. "
            "Không hỏi ngược để né trả lời."
        ),
        "reframe": (
            "Lượt này: mở ra một góc nhìn ít tự trách hơn. Không phủ nhận cảm xúc hiện tại."
        ),
    }
    return instructions.get(strategy, instructions["reflect"])


def select_strategy_with_legacy_reason(
    message: str,
    intent: str,
    emotion: str,
    policy: dict | None = None,
    mirror_mode: str = "deep_mirror",
    trust: float = 0.30,
    momentum: float = 0.0,
    arc: str = "none",
    bond_stage: str = "new",
) -> tuple[str, str]:
    return select_strategy_with_reason(
        message=message,
        intent=intent,
        emotion=emotion,
        trust=trust,
    )
