"""
Auth API router — signup, login, refresh, and profile endpoints.
PRD Section 9.2
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_db
from db.models import User, Firm, FirmMember
from auth.schemas import (
    SignupRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse,
)
from auth.service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from auth.dependencies import get_current_user
from core.response import ApiResponse
import jwt as pyjwt

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(req: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user and create their firm.
    Returns access + refresh tokens.
    """
    # Check if email already exists
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    # Check if phone already exists (if provided)
    if req.phone:
        existing_phone = await db.execute(select(User).where(User.phone == req.phone))
        if existing_phone.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this phone number already exists",
            )

    # Create user
    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        phone=req.phone,
    )
    db.add(user)
    await db.flush()  # Get the user ID

    # Create firm
    firm = Firm(name=req.firm_name)
    db.add(firm)
    await db.flush()

    # Create firm membership (owner role)
    membership = FirmMember(
        firm_id=firm.id,
        user_id=user.id,
        role="owner",
    )
    db.add(membership)
    await db.flush()

    # Generate tokens
    access_token = create_access_token(user.id, firm.id)
    refresh_token = create_refresh_token(user.id)

    return ApiResponse.ok(
        data={
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
            },
            "firm": {
                "id": firm.id,
                "name": firm.name,
            },
            "tokens": TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=900,  # 15 minutes
            ).model_dump(),
        }
    )


@router.post("/login")
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with email + password.
    Returns access + refresh tokens.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Get user's firm
    membership_result = await db.execute(
        select(FirmMember).where(FirmMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    firm_id = membership.firm_id if membership else None

    access_token = create_access_token(user.id, firm_id)
    refresh_token = create_refresh_token(user.id)

    return ApiResponse.ok(
        data={
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
            },
            "tokens": TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=900,
            ).model_dump(),
        }
    )


@router.post("/refresh")
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a refresh token for a new access + refresh token pair.
    """
    try:
        payload = decode_token(req.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired — please log in again",
        )
    except pyjwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Get firm
    membership_result = await db.execute(
        select(FirmMember).where(FirmMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()
    firm_id = membership.firm_id if membership else None

    new_access = create_access_token(user.id, firm_id)
    new_refresh = create_refresh_token(user.id)

    return ApiResponse.ok(
        data={
            "tokens": TokenResponse(
                access_token=new_access,
                refresh_token=new_refresh,
                expires_in=900,
            ).model_dump(),
        }
    )


@router.get("/me")
async def get_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Get the authenticated user's profile + firm info.
    """
    membership_result = await db.execute(
        select(FirmMember).where(FirmMember.user_id == user.id)
    )
    membership = membership_result.scalar_one_or_none()

    firm_data = None
    if membership:
        from db.models import Firm
        firm_result = await db.execute(select(Firm).where(Firm.id == membership.firm_id))
        firm = firm_result.scalar_one_or_none()
        if firm:
            firm_data = {
                "id": firm.id,
                "name": firm.name,
                "role": membership.role,
            }

    return ApiResponse.ok(
        data={
            "user": UserResponse(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                phone=user.phone,
                email_verified=user.email_verified,
                firm=firm_data,
                created_at=user.created_at,
            ).model_dump(),
        }
    )
