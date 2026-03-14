#!/usr/bin/env python3
"""
Simple import guard for production runtime.
Fails if root runtime files import modules from legacy candidates.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RUNTIME_FILES = [
    "app.py",
    "pipeline.py",
    "prompt_builder.py",
    "memory_engine.py",
    "memory_selector.py",
    "user_service.py",
    "llm_adapter.py",
    "logging_engine.py",
    "rate_limit_engine.py",
    "turn_trace_engine.py",
]

LEGACY_MODULES = {
    "response_policy",
    "response_policy_v2",
    "prompt_builder_backup",
    "pronoun_engine",
    "trust_engine",
    "user_state_engine",
    "internal_state_service",
    "presence_engine",
    "relational_continuity_engine",
    "temporal_self_engine",
    "familiarity_engine",
    "adaptive_tone_engine",
    "adaptive_personality_engine",
    "personality_dna_engine",
    "biological_engine",
    "consciousness_engine",
    "conversation_gravity_engine",
    "conversation_state_engine",
    "feedback_engine",
    "analytics_engine",
    "soul_dashboard",
    "memory_summary_engine",
    "memory_threading_engine",
    "memory_decay_engine",
    "memory_extraction_engine",
    "life_graph_engine",
    "listening_style_service",
    "memory_control_engine",
    "pattern_learning_engine",
    "momentum_engine",
}

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)", re.M)


def main() -> int:
    repo = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
    violations = []

    for fname in RUNTIME_FILES:
        path = repo / fname
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        imports = IMPORT_RE.findall(text)
        for imp in imports:
            root = imp.split(".")[0]
            if root in LEGACY_MODULES:
                violations.append({"file": fname, "import": imp})

    if violations:
        for v in violations:
            print(f"VIOLATION: {v['file']} imports legacy module {v['import']}")
        return 1

    print("OK: no legacy imports detected in runtime files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
