#!/usr/bin/env python3
"""
Pre-deploy migration — MEBOST Hải Đăng V2
Railway preDeployCommand: python migrate.py
"""
import sys, os

print("=" * 50)
print("MEBOST V2 — Pre-deploy migration")
print("=" * 50)

required = ["OPENROUTER_API_KEY", "SECRET_KEY"]
missing  = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"[FATAL] Missing env vars: {', '.join(missing)}")
    sys.exit(1)

db_url = os.environ.get("DATABASE_URL", "")
if db_url and db_url.startswith("postgres://"):
    os.environ["DATABASE_URL"] = db_url.replace("postgres://", "postgresql://", 1)
    print("[DB] Normalized DATABASE_URL")

print(f"[DB] Mode: {'PostgreSQL' if db_url else 'SQLite'}")

from db import init_db, ensure_data_dir
ensure_data_dir()
init_db()
print("[DB] Schema initialized OK")
print("Migration complete.")
