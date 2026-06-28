"""
FastAPI dependency for extracting and validating the current user from JWT.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_db
from db.models import User, FirmMember
from auth.service import decode_token
from db.rls import set_rls_context
import jwt as pyjwt

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Extract user from Bearer token. Raises 401 if token is invalid or user not found.
    After authentication, binds the user's firm_id to the PostgreSQL RLS context
    so that all subsequent queries in this request are automatically scoped to
    that firm (PRD ss11.1, ADR-002).
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type - expected access token",
            )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email not verified. Please verify your email address before accessing this resource.",
        )

    # RLS context binding
    # Resolve firm_id from JWT claim (fast path) or DB lookup (fallback).
    firm_id: str | None = payload.get("firm_id")
    if not firm_id:
        membership_result = await db.execute(
            select(FirmMember.firm_id).where(FirmMember.user_id == user.id)
        )
        firm_id = membership_result.scalar_one_or_none()
    await set_rls_context(db, firm_id)

    return user


async def require_totp_validated(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """
    Additional dependency for admin/owner routes that require TOTP to have been
    validated in the current session.  Checks the totp_ok claim in the JWT.

    Usage:
        @router.delete("/firm", dependencies=[Depends(require_totp_validated)])
    """
    token = credentials.credentials
    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    # Only enforce for users who have TOTP enabled
    if getattr(user, "totp_enabled", False):
        if not payload.get("totp_ok"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action requires TOTP verification. "
                       "POST /v1/auth/totp/validate and use the returned token.",
            )
    return user
