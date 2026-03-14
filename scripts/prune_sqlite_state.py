#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import get_db, db_mode  # type: ignore
from services.runtime_guard import is_sqlite_prune_enabled, sqlite_prune_days  # type: ignore


def main() -> None:
    if not is_sqlite_prune_enabled():
        print("[SKIP] ENABLE_SQLITE_PRUNE disabled")
        return

    if db_mode() != "sqlite":
        print("[SKIP] prune only intended for sqlite mode")
        return

    cutoff = (datetime.now(timezone.utc) - timedelta(days=sqlite_prune_days())).strftime("%Y-%m-%dT%H:%M:%SZ")
    db = get_db()
    cur = db.cursor()

    actions = []
    try:
        # Xóa rate limit cũ
        cur.execute("DELETE FROM rate_limits WHERE created_at < ?", (cutoff,))
        actions.append(("rate_limits", cur.rowcount))

        # Xóa signup rate limits cũ nếu có
        try:
            cur.execute("DELETE FROM signup_rate_limits WHERE created_at < ?", (cutoff,))
            actions.append(("signup_rate_limits", cur.rowcount))
        except Exception:
            pass

        # Giới hạn log decay quá cũ
        try:
            cur.execute("DELETE FROM memory_decay_logs WHERE decayed_at < ?", (cutoff,))
            actions.append(("memory_decay_logs", cur.rowcount))
        except Exception:
            pass

        # VACUUM để file DB gọn hơn
        db.commit()
        try:
            db.execute("VACUUM")
        except Exception:
            pass
        db.commit()
    finally:
        db.close()

    for table, count in actions:
        print(f"[OK] pruned {count} rows from {table}")


if __name__ == "__main__":
    main()
