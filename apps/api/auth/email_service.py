"""
Email delivery service for OTP codes.
Supports SMTP (dev/Gmail) and can be extended for AWS SES (production).
"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import aiosmtplib
from core.config import settings

logger = logging.getLogger(__name__)


def _build_otp_html(otp_code: str, purpose: str) -> str:
    """Build a styled HTML email body for OTP delivery."""
    if purpose == "verify_email":
        title = "Verify Your Email"
        heading = "Email Verification"
        message = "Use the code below to verify your email address and complete your registration."
    else:
        title = "Reset Your Password"
        heading = "Password Reset"
        message = "Use the code below to reset your password. If you didn't request this, please ignore this email."

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="utf-8"><title>{title}</title></head>
    <body style="margin:0;padding:0;background:#f4f6f9;font-family:'Segoe UI',Roboto,Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
        <tr><td align="center">
          <table width="420" cellpadding="0" cellspacing="0"
                 style="background:#ffffff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,0.08);overflow:hidden;">
            <!-- Header gradient bar -->
            <tr><td style="height:6px;background:linear-gradient(90deg,#3b82f6,#8b5cf6,#ec4899);"></td></tr>
            <tr><td style="padding:36px 32px 20px;">
              <h1 style="margin:0 0 8px;font-size:22px;font-weight:700;color:#1e293b;">{heading}</h1>
              <p style="margin:0 0 24px;font-size:15px;color:#64748b;line-height:1.5;">{message}</p>
              <!-- OTP Code -->
              <div style="text-align:center;margin:24px 0;">
                <div style="display:inline-block;padding:16px 36px;background:#f1f5f9;border-radius:12px;
                            letter-spacing:12px;font-size:32px;font-weight:700;color:#1e293b;
                            border:2px dashed #cbd5e1;">
                  {otp_code}
                </div>
              </div>
              <p style="margin:20px 0 0;font-size:13px;color:#94a3b8;text-align:center;">
                This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.
              </p>
            </td></tr>
            <!-- Footer -->
            <tr><td style="padding:16px 32px 24px;border-top:1px solid #f1f5f9;">
              <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
                Bank Statement Scanner &mdash; Secure document processing
              </p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </body>
    </html>
    """


async def send_otp_email(to_email: str, otp_code: str, purpose: str = "verify_email") -> bool:
    """
    Send an OTP code via email.

    Args:
        to_email: Recipient email address
        otp_code: 6-digit OTP code
        purpose: "verify_email" or "reset_password"

    Returns:
        True if sent successfully, False otherwise.
    """
    subject = (
        "Verify your email — Bank Statement Scanner"
        if purpose == "verify_email"
        else "Password reset code — Bank Statement Scanner"
    )

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain text fallback
    plain_text = (
        f"Your verification code is: {otp_code}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(_build_otp_html(otp_code, purpose), "html"))

    # In development, if no SMTP credentials are configured, log the OTP instead of sending
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.warning(
            "SMTP credentials not configured. OTP for %s (%s): %s",
            to_email, purpose, otp_code,
        )
        return True

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
        )
        logger.info("OTP email sent to %s (purpose=%s)", to_email, purpose)
        return True
    except Exception:
        logger.exception("Failed to send OTP email to %s", to_email)
        return False
