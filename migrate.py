#!/usr/bin/env python3
"""
Pre-deploy migration script cho Railway.
Chạy trước start command: python migrate.py

Railway config:
  "preDeployCommand": "python migrate.py"
"""
import sys, os, time

print("=" * 50)
print("MEBOST — Pre-deploy migration")
print("=" * 50)

# Validate env vars bắt buộc trước khi migrate
required = ["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", "11122233344455566677788899911122"]
missing  = [k for k in required if not os.environ.get(k)]
if missing:
    print(f"[FATAL] Missing env vars: {', '.join(missing)}")
    print("        Set these in Railway → Settings → Variables")
    sys.exit(1)

# Check DB mode
db_url = os.environ.get("DATABASE_URL", "")
if db_url:
    mode = "PostgreSQL"
    # Railway inject postgres:// nhưng SQLAlchemy cần postgresql://
    if db_url.startswith("postgres://"):
        os.environ["DATABASE_URL"] = db_url.replace("postgres://", "postgresql://", 1)
        print("[DB] Normalized DATABASE_URL: postgres:// → postgresql://")
else:
    mode = "SQLite (Volume hoặc local)"

print(f"[DB] Mode: {mode}")
print(f"[ENV] RAILWAY_ENVIRONMENT: {os.environ.get('RAILWAY_ENVIRONMENT','local')}")
print(f"[ENV] LOG_LEVEL: {os.environ.get('LOG_LEVEL','INFO')}")

# Chạy tất cả migrations theo thứ tự
t0 = time.time()
try:
    from db import init_db, migrate_db, migrate_accounts_schema, migrate_v13_schema
    print("[MIG] init_db...")
    init_db()
    print("[MIG] migrate_db...")
    migrate_db()
    print("[MIG] migrate_accounts_schema...")
    migrate_accounts_schema()
    print("[MIG] migrate_v13_schema...")
    migrate_v13_schema()

    from services.momentum_engine         import ensure_momentum_column
    from services.trust_engine            import ensure_trust_column
    from services.memory_threading_engine import ensure_thread_link_table
    from services.pronoun_engine          import ensure_pronoun_table
    from services.personality_dna_engine  import ensure_dna_table

    print("[MIG] ensure engine columns/tables...")
    ensure_momentum_column()
    ensure_trust_column()
    ensure_thread_link_table()
    ensure_pronoun_table()
    ensure_dna_table()

    elapsed = time.time() - t0
    print(f"[OK] All migrations completed in {elapsed:.2f}s")
    print("=" * 50)
    sys.exit(0)

except Exception as e:
    print(f"[FATAL] Migration failed: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)
