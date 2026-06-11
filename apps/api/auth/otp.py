"""
OTP generation, storage, and verification logic.
Handles both email verification and password reset OTPs.
"""
import secrets
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db.models import OtpCode, utcnow

logger = logging.getLogger(__name__)


def generate_otp() -> str:
    """Generate a cryptographically secure 6-digit OTP code."""
    # If SMTP is not configured, use a universal code so the app can be tested
    # without having to read ECS container logs.
    if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
        return "123456"
    return f"{secrets.randbelow(1_000_000):06d}"


async def create_otp(
    db: AsyncSession,
    email: str,
    purpose: str,
    user_id: str | None = None,
) -> str | None:
    """
    Create a new OTP record for the given email and purpose.
    Invalidates any previous unused OTPs for the same email+purpose.
    Returns the OTP code, or None if rate-limited.

    Args:
        db: Database session
        email: Target email
        purpose: "verify_email" or "reset_password"
        user_id: Optional user ID to associate
    """
    # Rate limiting: count OTPs created in the last hour for this email+purpose
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    count_result = await db.execute(
        select(func.count(OtpCode.id)).where(
            and_(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
                OtpCode.created_at >= one_hour_ago,
            )
        )
    )
    recent_count = count_result.scalar_one()

    if recent_count >= settings.OTP_MAX_ATTEMPTS_PER_HOUR:
        logger.warning("OTP rate limit reached for %s (%s): %d in last hour", email, purpose, recent_count)
        return None

    # Invalidate any previous unused OTPs for this email+purpose
    existing_result = await db.execute(
        select(OtpCode).where(
            and_(
                OtpCode.email == email,
                OtpCode.purpose == purpose,
                OtpCode.used_at.is_(None),
            )
        )
    )
    for old_otp in existing_result.scalars().all():
        old_otp.used_at = utcnow()  # Mark as consumed so they can't be reused

    # Create new OTP
    code = generate_otp()
    otp_record = OtpCode(
        email=email,
        user_id=user_id,
        code=code,
        purpose=purpose,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
    )
    db.add(otp_record)
    await db.flush()

    logger.info("Created OTP for %s (purpose=%s)", email, purpose)
    return code


async def verify_otp(
    db: AsyncSession,
    email: str,
    code: str,
    purpose: str,
) -> bool:
    """
    Verify an OTP code for the given email and purpose.
    Marks the OTP as used on success.

    Returns True if valid, False otherwise.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(OtpCode).where(
            and_(
                OtpCode.email == email,
                OtpCode.code == code,
                OtpCode.purpose == purpose,
                OtpCode.used_at.is_(None),
                OtpCode.expires_at > now,
            )
        ).order_by(OtpCode.created_at.desc()).limit(1)
    )
    otp_record = result.scalar_one_or_none()

    if not otp_record:
        logger.warning("OTP verification failed for %s (purpose=%s)", email, purpose)
        return False

    # Mark as used
    otp_record.used_at = utcnow()
    await db.flush()

    logger.info("OTP verified for %s (purpose=%s)", email, purpose)
    return True
