"""
Email delivery service for OTP codes.
Uses AWS SES in production (when EMAIL_PROVIDER=ses or AWS runtime is detected) and falls back to
SMTP (Gmail) for local development.

AWS IPs are blocked by Gmail SMTP — SES is the correct solution for production.
"""
import logging
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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


async def _send_via_ses(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    """Send email using AWS SES (boto3). Used in production on AWS."""
    try:
        import boto3

        from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME
        if not from_email:
            logger.error("SES sender is not configured. Set SMTP_FROM_EMAIL to a verified SES identity.")
            return False

        region_name = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1"
        client = boto3.client("ses", region_name=region_name)
        client.send_email(
            Source=f"{settings.SMTP_FROM_NAME} <{from_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": plain_text, "Charset": "UTF-8"},
                    "Html": {"Data": html_body, "Charset": "UTF-8"},
                },
            },
        )
        logger.info("OTP email sent via SES to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send OTP email via SES to %s", to_email)
        return False


async def _send_via_smtp(to_email: str, subject: str, plain_text: str, html_body: str) -> bool:
    """Send email via SMTP. Used for local development."""
    import aiosmtplib

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            start_tls=True,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
        )
        logger.info("OTP email sent via SMTP to %s", to_email)
        return True
    except Exception:
        logger.exception("Failed to send OTP email via SMTP to %s", to_email)
        return False


async def send_otp_email(to_email: str, otp_code: str, purpose: str = "verify_email") -> bool:
    """
    Send an OTP code via email.

    - In production (AWS ECS): uses AWS SES — avoids Gmail's block on AWS IPs.
    - In local development (SMTP credentials set): uses Gmail SMTP.
    - Fallback: logs OTP to console (dev mode without credentials).

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
    plain_text = (
        f"Your verification code is: {otp_code}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If you did not request this, please ignore this email."
    )
    html_body = _build_otp_html(otp_code, purpose)

    # ── Production: prefer AWS SES ──────────────────────────────
    # AWS blocks outbound Gmail SMTP from ECS/EC2 IPs.
    # Detect we're running on AWS by checking for ECS-specific env vars.
    running_on_aws = bool(
        os.environ.get("ECS_CONTAINER_METADATA_URI")
        or os.environ.get("ECS_CONTAINER_METADATA_URI_V4")
        or os.environ.get("AWS_EXECUTION_ENV")
    )
    if settings.EMAIL_PROVIDER.lower() == "ses" or running_on_aws:
        logger.info("Using SES for email delivery")
        return await _send_via_ses(to_email, subject, plain_text, html_body)

    # ── No SMTP credentials → log to console (dev fallback) ─────
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        logger.warning(
            "No email credentials configured. OTP for %s (%s): %s",
            to_email, purpose, otp_code,
        )
        return True

    # ── Local development: use SMTP ─────────────────────────────
    return await _send_via_smtp(to_email, subject, plain_text, html_body)
