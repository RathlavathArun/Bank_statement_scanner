"""
TOTP MFA API endpoints.

Endpoints:
  POST /v1/auth/totp/setup    — generate a new TOTP secret + QR code
  POST /v1/auth/totp/confirm  — verify first-time code to activate TOTP
  POST /v1/auth/totp/validate — validate code during login; returns TOTP-augmented JWT
  POST /v1/auth/totp/disable  — disable TOTP (requires valid code + password)

Only admin and owner role users are required to use TOTP (enforced by
require_totp_validated in auth/dependencies.py for sensitive routes).
Standard member/viewer roles may optionally set up TOTP but are not forced.

PRD reference: Phase 1 Task 8.
"""
from __future__ import annotations

import logging

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user, get_mfa_user
from auth.service import create_access_token, decode_token, verify_password
from auth.totp import (
    decrypt_secret,
    encrypt_secret,
    generate_qr_code_data_url,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code,
)
from core.config import settings
from core.response import ApiResponse
from db.database import get_db
from db.models import FirmMember, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth/totp", tags=["TOTP MFA"])


# ─── Request / Response schemas ─────────────────────────────────────────────

class TotpConfirmRequest(BaseModel):
    code: str  # 6-digit TOTP code


class TotpValidateRequest(BaseModel):
    code: str  # 6-digit TOTP code
    # The base access token from /login — we augment it with totp_ok=True
    access_token: str


class TotpDisableRequest(BaseModel):
    code: str      # current valid TOTP code (proves device possession)
    password: str  # current account password (proves account ownership)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _create_totp_validated_token(user_id: str, firm_id: str | None) -> str:
    """Create a short-lived access token that carries totp_ok=True."""
    return create_access_token(user_id, firm_id, totp_ok=True)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/setup")
async def totp_setup(
    user: User = Depends(get_mfa_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new TOTP secret and return the provisioning URI + QR code.
    The secret is stored (encrypted) but TOTP is NOT yet enabled until
    /confirm succeeds.
    """
    secret = generate_totp_secret()
    totp_uri = get_totp_uri(secret, user.email)
    qr_data_url = generate_qr_code_data_url(totp_uri)

    # Store encrypted secret temporarily; totp_enabled stays False
    user.totp_secret_enc = encrypt_secret(secret)
    await db.commit()

    return ApiResponse.ok(data={
        "totp_uri": totp_uri,
        "qr_code": qr_data_url,
        "message": "Scan the QR code with your authenticator app, then POST the 6-digit code to /v1/auth/totp/confirm",
    })


@router.post("/confirm")
async def totp_confirm(
    req: TotpConfirmRequest,
    user: User = Depends(get_mfa_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm TOTP setup by verifying the first code from the authenticator app.
    Marks totp_enabled=True once the code is valid.
    """
    if not user.totp_secret_enc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP setup has not been initiated. POST /v1/auth/totp/setup first.",
        )

    try:
        secret = decrypt_secret(user.totp_secret_enc)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not decrypt TOTP secret. Please re-run setup.",
        )

    if not verify_totp_code(secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code. Ensure your device clock is correct and try again.",
        )

    user.totp_enabled = True
    await db.commit()
    logger.info("TOTP enabled for user=%s", user.id)

    membership = await db.execute(select(FirmMember).where(FirmMember.user_id == user.id))
    firm_id = membership.scalar_one_or_none()
    return ApiResponse.ok(data={
        "totp_enabled": True,
        "access_token": _create_totp_validated_token(
            user.id, firm_id.firm_id if firm_id else None
        ),
        "message": "TOTP MFA is now active on your account. Keep your recovery codes safe.",
    })


@router.post("/validate")
async def totp_validate(
    req: TotpValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Validate a TOTP code during login and return a TOTP-augmented access token.

    Flow:
      1. Client POSTs /v1/auth/login → gets access_token (totp_ok absent)
      2. Client POSTs /v1/auth/totp/validate with that token + 6-digit code
      3. Server returns a new access_token with totp_ok=True
      4. Client uses the new token for all subsequent requests to protected routes
    """
    # Decode the provided access token to get user_id
    try:
        payload = decode_token(req.access_token)
        if payload.get("type") != "access":
            raise ValueError("Not an access token")
        user_id = payload["sub"]
    except (pyjwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is not enabled on this account.",
        )

    try:
        secret = decrypt_secret(user.totp_secret_enc)
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="TOTP configuration error.")

    if not verify_totp_code(secret, req.code):
        logger.warning("Failed TOTP validation attempt for user=%s", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code.",
        )

    # Look up firm_id for the new token
    firm_id: str | None = payload.get("firm_id")
    if not firm_id:
        m = await db.execute(select(FirmMember.firm_id).where(FirmMember.user_id == user.id))
        firm_id = m.scalar_one_or_none()

    totp_token = _create_totp_validated_token(user.id, firm_id)
    logger.info("TOTP validated for user=%s", user.id)

    return ApiResponse.ok(data={
        "access_token": totp_token,
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "message": "TOTP validated. Use this access_token for subsequent requests.",
    })


@router.post("/disable")
async def totp_disable(
    req: TotpDisableRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Disable TOTP on the account. Requires both a valid current TOTP code
    AND the account password (dual-factor confirmation).
    """
    if not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="TOTP is not enabled on this account.",
        )

    # Verify password
    from auth.service import verify_password as vp
    if not vp(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password.",
        )

    # Verify TOTP code
    secret = decrypt_secret(user.totp_secret_enc)
    if not verify_totp_code(secret, req.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code.",
        )

    user.totp_enabled = False
    user.totp_secret_enc = None
    await db.commit()
    logger.info("TOTP disabled for user=%s", user.id)

    return ApiResponse.ok(data={
        "totp_enabled": False,
        "message": "TOTP MFA has been disabled on your account.",
    })
