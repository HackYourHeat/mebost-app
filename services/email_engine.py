# --------------------------------------------------
# Email Engine — MEBOST Hải Đăng V1.1
# Lightweight SMTP sender.
# Config từ env — swap provider mà không đổi code.
# --------------------------------------------------

from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

log = logging.getLogger("mebost.email")

# --------------------------------------------------
# Config from environment
# --------------------------------------------------

_SMTP_HOST = os.getenv("SMTP_HOST", "")
_SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER = os.getenv("SMTP_USER", "")
_SMTP_PASS = os.getenv("SMTP_PASS", "")
_SMTP_FROM = os.getenv("SMTP_FROM", "Hải Đăng <noreply@haidang.app>")
_APP_DOMAIN = os.getenv("APP_DOMAIN", "https://haidang.app")


# --------------------------------------------------
# Core sender
# --------------------------------------------------

def _send_smtp(to_email: str, subject: str, body_html: str) -> bool:
    """
    Gửi email qua SMTP.
    Trả về True nếu thành công, False nếu lỗi.
    """
    if not _SMTP_HOST or not _SMTP_USER:
        # Dev mode: chỉ log, không gửi thật
        log.warning("SMTP chưa config — email sẽ chỉ được log (dev mode)")
        log.info("DEV EMAIL → %s | Subject: %s", to_email, subject)
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = _SMTP_FROM
        msg["To"]      = to_email
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(_SMTP_USER, _SMTP_PASS)
            server.sendmail(_SMTP_FROM, [to_email], msg.as_string())

        log.info("EMAIL_SENT to=%s subject=%s", to_email, subject)
        return True

    except Exception as exc:
        log.error("EMAIL_FAILED to=%s error=%s", to_email, exc)
        return False


# --------------------------------------------------
# Public: verification email
# --------------------------------------------------

def send_verification_email(to_email: str, token: str) -> bool:
    """
    Gửi email xác nhận tài khoản.

    Args:
        to_email : địa chỉ email người nhận
        token    : verification token (không log đầy đủ)

    Returns:
        True nếu gửi thành công hoặc dev mode
    """
    verify_url = f"{_APP_DOMAIN}/auth/verify?token={token}"

    subject = "Xác nhận email cho Hải Đăng"

    body = f"""
<html><body style="font-family: Georgia, serif; color: #2c2c2c; max-width: 520px; margin: 40px auto; padding: 0 20px;">
  <h2 style="color: #1a3a4a;">🌊 Hải Đăng</h2>
  <p>Bạn vừa đăng ký tài khoản trên Hải Đăng.</p>
  <p>Nhấp vào link bên dưới để xác nhận email và bảo vệ ký ức của bạn:</p>
  <p style="margin: 28px 0;">
    <a href="{verify_url}"
       style="background:#1a3a4a; color:#fff; padding: 12px 24px;
              text-decoration:none; border-radius:6px; font-size:15px;">
      Xác nhận email
    </a>
  </p>
  <p style="color:#888; font-size:13px;">Link này hết hạn sau 24 giờ.</p>
  <p style="color:#888; font-size:13px;">Nếu bạn không đăng ký, có thể bỏ qua email này.</p>
  <hr style="border:none; border-top:1px solid #eee; margin: 32px 0;">
  <p style="color:#aaa; font-size:12px;">Hải Đăng — AI companion</p>
</body></html>
"""

    log.info("verification_sent email=%s token_prefix=%s", to_email, token[:8])
    return _send_smtp(to_email, subject, body)
