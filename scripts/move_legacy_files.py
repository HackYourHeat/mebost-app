#!/usr/bin/env python3
"""
Move legacy/experimental files out of root safely.

Usage:
    python scripts/move_legacy_files.py /path/to/repo --apply
    python scripts/move_legacy_files.py /path/to/repo

Default mode is dry-run.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

LEGACY = [
    "response_policy.py",
    "response_policy_v2.py",
    "prompt_builder_backup.py",
    "pronoun_engine.py",
    "trust_engine.py",
    "user_state_engine.py",
    "internal_state_service.py",
    "presence_engine.py",
    "relational_continuity_engine.py",
    "temporal_self_engine.py",
    "familiarity_engine.py",
    "adaptive_tone_engine.py",
    "adaptive_personality_engine.py",
    "personality_dna_engine.py",
    "biological_engine.py",
    "consciousness_engine.py",
    "conversation_gravity_engine.py",
    "conversation_state_engine.py",
    "feedback_engine.py",
    "analytics_engine.py",
    "soul_dashboard.py",
    "memory_summary_engine.py",
    "memory_threading_engine.py",
    "memory_decay_engine.py",
    "memory_extraction_engine.py",
    "life_graph_engine.py",
    "listening_style_service.py",
    "memory_control_engine.py",
    "pattern_learning_engine.py",
    "momentum_engine.py",
]

EXPERIMENTAL = []

KEEP_IN_ROOT = {
    "app.py",
    "db.py",
    "llm_adapter.py",
    "logging_engine.py",
    "rate_limit_engine.py",
    "user_service.py",
    "pipeline.py",
    "prompt_builder.py",
    "memory_engine.py",
    "memory_selector.py",
    "turn_trace_engine.py",
    # compat shim, optional to move later
    "response_strategy_engine.py",
}


def move_files(repo: Path, apply: bool = False) -> dict:
    legacy_dir = repo / "legacy"
    experimental_dir = repo / "experimental"
    legacy_dir.mkdir(exist_ok=True)
    experimental_dir.mkdir(exist_ok=True)

    report = {"moved": [], "missing": [], "kept": sorted(KEEP_IN_ROOT)}

    for name in LEGACY:
        src = repo / name
        dst = legacy_dir / name
        if not src.exists():
            report["missing"].append(name)
            continue
        report["moved"].append({"from": str(src), "to": str(dst)})
        if apply:
            shutil.move(str(src), str(dst))

    for name in EXPERIMENTAL:
        src = repo / name
        dst = experimental_dir / name
        if not src.exists():
            report["missing"].append(name)
            continue
        report["moved"].append({"from": str(src), "to": str(dst)})
        if apply:
            shutil.move(str(src), str(dst))

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", help="Path to repository root")
    parser.add_argument("--apply", action="store_true", help="Actually move files")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.exists():
        raise SystemExit(f"Repo path does not exist: {repo}")

    report = move_files(repo, apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
