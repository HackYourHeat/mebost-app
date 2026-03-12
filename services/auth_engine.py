# --------------------------------------------------
# Auth Engine — MEBOST Hải Đăng V1.1
# Account Lite: signup / login / logout / verify
# Guest → account promotion với full continuity.
# MVP-ready. Không JWT, không OAuth, không Redis.
# --------------------------------------------------

from __future__ import annotations

import logging
import re
import secrets
from datetime import datetime, timezone, timedelta

from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db, utc_now_iso

log = logging.getLogger("mebost.auth")

# --------------------------------------------------
# Constants
# --------------------------------------------------

GUEST_RETENTION_DAYS       = 14
VERIFICATION_EXPIRES_HOURS = 24
MIN_PASSWORD_LEN           = 8
SIGNUP_RATE_LIMIT          = 3     # max per IP per hour

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

def _generate_token() -> str:
    return secrets.token_urlsafe(32)

def _validate_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))

def _validate_password(password: str) -> bool:
    return len(password) >= MIN_PASSWORD_LEN


# --------------------------------------------------
# Signup rate limit
# --------------------------------------------------

def _check_signup_rate_limit(ip: str) -> bool:
    """
    True → allowed.  False → too many signups from this IP.
    """
    cutoff = _iso(_now_utc() - timedelta(hours=1))
    db = get_db()
    try:
        count = db.execute(
            """SELECT COUNT(*) FROM signup_rate_limits
               WHERE ip_address = ? AND created_at > ?""",
            (ip, cutoff),
        ).fetchone()[0]
        return count < SIGNUP_RATE_LIMIT
    finally:
        db.close()

def _record_signup_attempt(ip: str) -> None:
    db = get_db()
    try:
        db.execute(
            "INSERT INTO signup_rate_limits (ip_address, created_at) VALUES (?, ?)",
            (ip, utc_now_iso()),
        )
        db.commit()
    finally:
        db.close()


# --------------------------------------------------
# Account lookup helpers
# --------------------------------------------------

def _get_account_by_email(email: str) -> dict | None:
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM accounts WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()

def _get_account_by_token(token: str) -> dict | None:
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM accounts WHERE verification_token = ?", (token,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()

def _get_user_by_account(account_id: str) -> dict | None:
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM users WHERE account_id = ? AND is_guest = 0 LIMIT 1",
            (account_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


# --------------------------------------------------
# Guest promotion
# --------------------------------------------------

def _promote_guest_to_account(user_id: str, account_id: str) -> None:
    """
    Bind guest user_id → account.
    Giữ nguyên toàn bộ messages, memory, sessions.
    """
    db  = get_db()
    now = utc_now_iso()
    try:
        db.execute(
            """UPDATE users
               SET is_guest         = 0,
                   account_id       = ?,
                   guest_expires_at = NULL
               WHERE user_id = ?""",
            (account_id, user_id),
        )
        db.commit()
        log.info("guest_promoted_to_account user_id=%s account_id=%s", user_id, account_id)
    finally:
        db.close()


# --------------------------------------------------
# Public: signup
# --------------------------------------------------

def signup(
    email: str,
    password: str,
    guest_user_id: str,
    ip: str = "unknown",
) -> dict:
    """
    Tạo account mới và promote guest user.

    Returns:
        {"ok": True, "account_id": str, "message": str}
        {"ok": False, "error": str, "code": int}
    """
    log.info("signup_attempt email=%s ip=%s", email, ip)

    # Rate limit
    if not _check_signup_rate_limit(ip):
        log.warning("signup_rate_limited ip=%s", ip)
        return {"ok": False, "error": "Quá nhiều lần đăng ký. Thử lại sau.", "code": 429}

    _record_signup_attempt(ip)

    # Validate
    if not _validate_email(email):
        return {"ok": False, "error": "Email không hợp lệ.", "code": 400}
    if not _validate_password(password):
        return {"ok": False, "error": f"Mật khẩu phải ít nhất {MIN_PASSWORD_LEN} ký tự.", "code": 400}

    email_lower = email.strip().lower()

    # Duplicate check
    if _get_account_by_email(email_lower):
        return {"ok": False, "error": "Email này đã được đăng ký.", "code": 409}

    # Create account
    account_id  = secrets.token_hex(16)
    password_hash = generate_password_hash(password)
    token       = _generate_token()
    token_exp   = _iso(_now_utc() + timedelta(hours=VERIFICATION_EXPIRES_HOURS))
    now         = utc_now_iso()

    db = get_db()
    try:
        db.execute(
            """INSERT INTO accounts
               (id, email, password_hash, email_verified,
                verification_token, verification_expires, created_at, is_active)
               VALUES (?,?,?,0,?,?,?,1)""",
            (account_id, email_lower, password_hash, token, token_exp, now),
        )
        db.commit()
    finally:
        db.close()

    # Promote guest
    _promote_guest_to_account(guest_user_id, account_id)

    log.info("signup_success account_id=%s email=%s", account_id, email_lower)
    return {
        "ok":         True,
        "account_id": account_id,
        "user_id":    guest_user_id,
        "verification_token": token,    # caller passes to email_engine
        "message":    "Đăng ký thành công. Kiểm tra email để xác nhận.",
    }


# --------------------------------------------------
# Public: verify email
# --------------------------------------------------

def verify_email(token: str) -> dict:
    """
    Xác nhận email qua token.
    """
    account = _get_account_by_token(token)
    if not account:
        log.warning("verification_failed reason=token_not_found")
        return {"ok": False, "error": "Token không hợp lệ.", "code": 400}

    expires = _parse_iso(account.get("verification_expires", ""))
    if expires and _now_utc() > expires:
        log.warning("verification_failed reason=expired account_id=%s", account["id"])
        return {"ok": False, "error": "Token đã hết hạn.", "code": 400}

    db = get_db()
    try:
        db.execute(
            """UPDATE accounts
               SET email_verified       = 1,
                   verification_token   = NULL,
                   verification_expires = NULL
               WHERE id = ?""",
            (account["id"],),
        )
        db.commit()
    finally:
        db.close()

    log.info("verification_success account_id=%s", account["id"])
    return {"ok": True, "message": "Email đã được xác nhận."}


# --------------------------------------------------
# Public: login
# --------------------------------------------------

def login(email: str, password: str) -> dict:
    """
    Login bằng email + password.
    Trả về account_id và user_id để frontend lưu.
    """
    email_lower = email.strip().lower()
    account = _get_account_by_email(email_lower)

    if not account or not check_password_hash(account["password_hash"], password):
        log.warning("login_failed email=%s", email_lower)
        return {"ok": False, "error": "Email hoặc mật khẩu không đúng.", "code": 401}

    if not account["is_active"]:
        return {"ok": False, "error": "Tài khoản đã bị vô hiệu hoá.", "code": 403}

    # Tìm user_id gắn với account
    user = _get_user_by_account(account["id"])
    user_id = user["user_id"] if user else None

    log.info("login_success account_id=%s", account["id"])
    return {
        "ok":             True,
        "account_id":     account["id"],
        "user_id":        user_id,
        "email_verified": account["email_verified"],
        "message":        "Đăng nhập thành công.",
    }


# --------------------------------------------------
# Public: logout (stateless MVP)
# --------------------------------------------------

def logout() -> dict:
    """
    MVP logout — frontend xoá local state.
    """
    return {"ok": True, "message": "Đã đăng xuất."}


# --------------------------------------------------
# Public: get account info
# --------------------------------------------------

def get_account_info(account_id: str) -> dict | None:
    db = get_db()
    try:
        row = db.execute(
            "SELECT id, email, email_verified, created_at FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()


# --------------------------------------------------
# Self-test (no DB needed)
# --------------------------------------------------

def test_auth_engine() -> None:
    """
    Test validation helpers mà không cần DB.
    """
    print("─── Auth Engine — Validation Tests ───")
    email_cases = [
        ("user@example.com",   True),
        ("bad-email",          False),
        ("@nodomain.com",      False),
        ("a@b.co",             True),
    ]
    for email, expect in email_cases:
        ok = _validate_email(email) == expect
        print(f"  {'OK  ' if ok else 'FAIL'}  email: {email}")

    pw_cases = [
        ("short",          False),
        ("12345678",       True),
        ("my_secure_pass", True),
    ]
    for pw, expect in pw_cases:
        ok = _validate_password(pw) == expect
        print(f"  {'OK  ' if ok else 'FAIL'}  password len={len(pw)}")

    print("──────────────────────────────────────")


if __name__ == "__main__":
    test_auth_engine()
