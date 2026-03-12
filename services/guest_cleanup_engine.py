# --------------------------------------------------
# Guest Cleanup Engine — MEBOST Hải Đăng V1.1
# --------------------------------------------------
# Xóa data của guest đã hết hạn.
# KHÔNG bao giờ xóa account-owned user (is_guest=0).
# --------------------------------------------------

from __future__ import annotations

import logging
from datetime import datetime, timezone

from db import get_db, utc_now_iso

log = logging.getLogger("mebost.guest_cleanup")


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------
# Core cleanup
# --------------------------------------------------

def cleanup_expired_guests() -> int:
    """
    Tìm và xóa toàn bộ data của guest user đã hết hạn.

    Safety rules:
    - Chỉ xóa user có is_guest = 1
    - Chỉ xóa nếu guest_expires_at < now
    - KHÔNG bao giờ xóa nếu is_guest = 0 (account-owned)

    Returns:
        Số guest bị cleanup
    """
    now = _now_iso()
    db  = get_db()

    try:
        # Tìm guest đã hết hạn — double-check is_guest=1
        expired = db.execute(
            """SELECT user_id FROM users
               WHERE is_guest         = 1
                 AND guest_expires_at IS NOT NULL
                 AND guest_expires_at < ?""",
            (now,),
        ).fetchall()

        if not expired:
            log.info("expired_guest_cleanup_count=0")
            return 0

        user_ids = [r["user_id"] for r in expired]
        placeholders = ",".join("?" * len(user_ids))

        # Cascade delete theo thứ tự phụ thuộc
        tables = [
            "rate_limits",
            "memory_decay_logs",
            "memory_summaries",
            "memory_nodes",
            "emotion_logs",
            "messages",
            "sessions",
        ]
        for table in tables:
            # Chỉ rate_limits có thể không có user_id — guard
            try:
                db.execute(
                    f"DELETE FROM {table} WHERE user_id IN ({placeholders})",
                    user_ids,
                )
            except Exception as exc:
                log.warning("cleanup_table_skip table=%s error=%s", table, exc)

        # Xóa life graph data nếu tồn tại
        for lg_table in ("life_threads", "life_edges", "life_nodes"):
            try:
                db.execute(
                    f"DELETE FROM {lg_table} WHERE user_id IN ({placeholders})",
                    user_ids,
                )
            except Exception:
                pass  # table chưa tồn tại → bỏ qua

        # Cuối cùng xóa users row
        db.execute(
            f"DELETE FROM users WHERE user_id IN ({placeholders}) AND is_guest = 1",
            user_ids,
        )

        db.commit()

        count = len(user_ids)
        log.info("expired_guest_cleanup_count=%d", count)
        return count

    finally:
        db.close()


def get_guest_stats(include_expired: bool = True) -> dict:
    """
    Thống kê guest hiện tại — dùng để debug / admin.

    Returns:
        {total_guests, expired_guests, active_guests}
    """
    now = _now_iso()
    db  = get_db()
    try:
        total = db.execute(
            "SELECT COUNT(*) FROM users WHERE is_guest = 1"
        ).fetchone()[0]

        expired = db.execute(
            """SELECT COUNT(*) FROM users
               WHERE is_guest = 1
                 AND guest_expires_at IS NOT NULL
                 AND guest_expires_at < ?""",
            (now,),
        ).fetchone()[0]

        return {
            "total_guests":  total,
            "expired_guests": expired,
            "active_guests":  total - expired,
        }
    finally:
        db.close()
