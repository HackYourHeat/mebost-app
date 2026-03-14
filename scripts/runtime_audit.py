#!/usr/bin/env python3
"""
Runtime audit cho repo MEBOST.

Mục tiêu:
- kiểm tra file runtime lõi có tồn tại
- cảnh báo import nhầm legacy/
- rà các endpoint/debug file mong đợi
- in ra tóm tắt dễ đọc

Cách chạy:
    python scripts/runtime_audit.py .
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(".").resolve()

RUNTIME_FILES = [
    ROOT / "app.py",
    ROOT / "services" / "pipeline.py",
    ROOT / "services" / "prompt_builder.py",
    ROOT / "services" / "memory_engine.py",
    ROOT / "services" / "memory_selector.py",
    ROOT / "services" / "turn_trace_engine.py",
]

WATCH_FOR_STRINGS = {
    ROOT / "app.py": ["/debug/turn", "pipeline_version", "trace"],
    ROOT / "services" / "pipeline.py": ["select_strategy_with_reason", "detect_emotion", "detect_intent"],
    ROOT / "services" / "prompt_builder.py": ["build_system_prompt", "build_user_prompt"],
}

SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules"}


def ok(msg: str) -> None:
    print(f"✓ {msg}")


def warn(msg: str) -> None:
    print(f"⚠ {msg}")


def fail(msg: str) -> None:
    print(f"✗ {msg}")


failed = 0

print(f"Runtime audit root: {ROOT}")
print("─" * 60)

# 1. Required files
for fp in RUNTIME_FILES:
    if fp.exists():
        ok(f"exists: {fp.relative_to(ROOT)}")
    else:
        fail(f"missing: {fp.relative_to(ROOT)}")
        failed += 1

# 2. Required symbols / strings
for fp, tokens in WATCH_FOR_STRINGS.items():
    if not fp.exists():
        continue
    text = fp.read_text(encoding="utf-8", errors="replace")
    for token in tokens:
        if token in text:
            ok(f"{fp.relative_to(ROOT)} contains '{token}'")
        else:
            warn(f"{fp.relative_to(ROOT)} does not contain '{token}'")

# 3. Import scan: runtime files should not import legacy.*
print("─" * 60)
print("Scanning imports...")
for fp in ROOT.rglob("*.py"):
    if any(part in SKIP_DIRS for part in fp.parts):
        continue
    if "legacy" in fp.parts:
        continue
    try:
        source = fp.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as e:
        fail(f"syntax error in {fp.relative_to(ROOT)}: {e}")
        failed += 1
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("legacy") or ".legacy" in module:
                fail(f"legacy import in {fp.relative_to(ROOT)}: from {module} import ...")
                failed += 1
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith("legacy"):
                    fail(f"legacy import in {fp.relative_to(ROOT)}: import {name}")
                    failed += 1

# 4. Optional sanity: tests and scripts
print("─" * 60)
for rel in [
    "tests/smoke_test.py",
    "tests/debug_turn_test.py",
    "tests/pipeline_integration_test.py",
    "tests/memory_runtime_test.py",
    "scripts/runtime_audit.py",
]:
    fp = ROOT / rel
    if fp.exists():
        ok(f"exists: {rel}")
    else:
        warn(f"missing optional file: {rel}")

print("─" * 60)
if failed:
    fail(f"runtime audit finished with {failed} issue(s)")
    sys.exit(1)
ok("runtime audit passed")
