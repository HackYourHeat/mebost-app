# --------------------------------------------------
# Turn Trace Engine — MEBOST V2
# --------------------------------------------------
# Ghi lại vì sao một lượt chat đi đến quyết định cuối cùng.
# Không gọi LLM. Không ghi DB. Chỉ tạo JSON debug an toàn.
# --------------------------------------------------

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceStep:
    stage: str
    value: Any
    reason: str = ""


@dataclass
class TurnTrace:
    user_id: str = ""
    session_id: str = ""
    message: str = ""
    language: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    def add(self, stage: str, value: Any, reason: str = "") -> None:
        self.steps.append(asdict(TraceStep(stage=stage, value=value, reason=reason)))

    def set_artifact(self, key: str, value: Any) -> None:
        self.artifacts[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "message": self.message,
            "language": self.language,
            "steps": self.steps,
            "artifacts": self.artifacts,
        }


# --------------------------------------------------
# Reason helpers
# --------------------------------------------------

_EMOTION_KEYWORDS = {
    "sad": ["buồn", "khóc", "nhớ", "cô đơn", "trống", "mất mát", "sad", "lonely", "hurt"],
    "anxious": ["lo", "lo lắng", "sợ", "bất an", "căng thẳng", "stress", "anxious", "panic"],
    "tired": ["mệt", "kiệt sức", "nặng nề", "uể oải", "tired", "exhausted", "burned out"],
    "angry": ["tức", "giận", "bực", "angry", "mad", "frustrated"],
    "happy": ["vui", "hạnh phúc", "tuyệt", "hào hứng", "happy", "joy", "excited"],
}

_HELP_PATTERNS = [
    "khuyên", "lời khuyên", "nên làm gì", "phải làm gì", "hướng giải quyết",
    "help me", "what should i do", "tell me what to do", "advise me",
]
_VENT_PATTERNS = [
    "chỉ muốn nói", "chỉ muốn kể", "tâm sự thôi", "không cần giải pháp",
    "just want to vent", "just need to talk",
]
_STUCK_PATTERNS = [
    "không biết phải làm gì", "không biết làm sao", "mình đang rối", "tôi đang rối",
    "i don't know what to do", "i'm lost", "i'm stuck", "không biết bắt đầu từ đâu",
]
_FRUSTRATION_PATTERNS = [
    "bạn cứ hỏi", "bạn không giúp", "cứ hỏi ngược", "không giúp gì",
    "just answer", "stop asking", "you keep asking", "you're not helping",
]
_SELF_ATTACK_PATTERNS = [
    "vô dụng", "ăn bám", "thất bại rồi", "không xứng",
    "i'm worthless", "i'm useless", "i'm a failure", "i hate myself",
]

_HIGH_IMPORTANCE = ["hãy nhớ", "remember this", "tên mình là", "my name is", "gọi mình là"]
_MEDIUM_IMPORTANCE = ["công việc", "gia đình", "dự án", "project", "family", "career", "relationship"]


def emotion_reason(message: str, emotion: str, intensity: int) -> str:
    low = message.lower()
    matched = [kw for kw in _EMOTION_KEYWORDS.get(emotion, []) if kw in low]
    if matched:
        return f"matched keywords={matched[:4]}, intensity={intensity}"
    return f"no strong keyword match, fallback emotion={emotion}, intensity={intensity}"


def intent_reason(message: str, intent: str) -> str:
    low = message.lower()

    pattern_map = {
        "help": _HELP_PATTERNS,
        "vent": _VENT_PATTERNS,
        "stuck": _STUCK_PATTERNS,
        "frustrated": _FRUSTRATION_PATTERNS,
        "self_attack": _SELF_ATTACK_PATTERNS,
        "question": ["?"],
    }

    matched = [kw for kw in pattern_map.get(intent, []) if kw in low]
    if matched:
        return f"matched patterns={matched[:4]}"
    return f"fallback intent={intent}"


def importance_reason(message: str, importance: int) -> str:
    low = message.lower()
    reasons: list[str] = []

    if any(s in low for s in _HIGH_IMPORTANCE):
        reasons.append("high_signal")
    elif any(s in low for s in _MEDIUM_IMPORTANCE):
        reasons.append("medium_signal")
    else:
        reasons.append("baseline")

    if len(message.strip()) > 150:
        reasons.append("len>150")

    return f"importance={importance} because {', '.join(reasons)}"


def trust_reason(updated: bool, before: float, after: float) -> str:
    if updated:
        return f"trust updated: {before:.3f} → {after:.3f}"
    return f"trust reused: {after:.3f}"


def pronoun_reason(ai_pronoun: str, user_pronoun: str) -> str:
    return f"resolved pronouns={ai_pronoun}/{user_pronoun}"


def pipeline_strategy_reason(intent: str, emotion: str, trust: float) -> str:
    if intent == "frustrated":
        return "intent=frustrated → engage"
    if intent == "self_attack":
        return f"intent=self_attack + trust={trust:.2f} → {'reframe' if trust >= 0.60 else 'comfort'}"
    if intent in ("help", "stuck"):
        return f"intent={intent} → guide"
    if intent == "vent":
        return "intent=vent → reflect"
    if emotion in ("sad", "anxious", "tired", "angry"):
        return f"heavy emotion={emotion} → reflect"
    return "default → reflect"


def memory_reason(memory_saved: bool, selected_memory: str, candidate_count: int) -> str:
    if not memory_saved and candidate_count == 0:
        return "message not stored or no active memory candidates"
    if not selected_memory.strip():
        return f"memory_saved={memory_saved}, but nothing selected for injection"
    return (
        f"memory_saved={memory_saved}, selected_memory_chars={len(selected_memory)}, "
        f"candidates={candidate_count}"
    )
