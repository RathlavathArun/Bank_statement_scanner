"""
Auth API router — signup, login, refresh, profile, email verification,
and password reset endpoints.
PRD Section 9.2
"""
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.database import get_db
from db.models import User, Firm, FirmMember, OTP
from auth.schemas import (
    SignupRequest, LoginRequest, RefreshRequest,
    VerifyEmailRequest, ResendOtpRequest,
    ForgotPasswordRequest, ResetPasswordRequest,
    TokenResponse, UserResponse,
    PhoneLoginRequest, PhoneLoginVerifyRequest,
    ForgotPasswordRequest, ResetPasswordRequest
)
import random
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from auth.service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token,
)
from auth.dependencies import get_current_user
from auth.otp import create_otp, verify_otp
from auth.email_service import send_otp_email
from core.response import ApiResponse
import jwt as pyjwt
import os
from twilio.rest import Client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    req: SignupRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user and create their firm.
    Sends email verification OTP. Returns access + refresh tokens.
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

    # Generate OTP and send verification email
    otp_code = await create_otp(db, email=req.email, purpose="verify_email", user_id=user.id)
    if otp_code is None:
        # Rate limited — still create the account but inform the user
        logger.warning("OTP rate-limited during signup for %s — account created but no email sent", req.email)
    else:
        background_tasks.add_task(send_otp_email, req.email, otp_code, "verify_email")

    # Generate tokens
    access_token = create_access_token(user.id, firm.id)
    refresh_token = create_refresh_token(user.id)

    await db.commit()

    return ApiResponse.ok(
        data={
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "email_verified": False,
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
    Returns access + refresh tokens and email_verified status.
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
                "email_verified": user.email_verified,
            },
            "tokens": TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=900,
            ).model_dump(),
        }
    )


@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """
    Verify a user's email address using the 6-digit OTP code.
    """
    # Find the user
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.email_verified:
        return ApiResponse.ok(data={"message": "Email already verified"})

    # Verify the OTP
    is_valid = await verify_otp(db, email=req.email, code=req.code, purpose="verify_email")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    # Mark email as verified
    user.email_verified = True
    await db.commit()

    # Generate fresh tokens
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
                "email_verified": True,
            },
            "tokens": TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=900,
            ).model_dump(),
        }
    )


@router.post("/resend-otp")
async def resend_otp(
    req: ResendOtpRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Resend an OTP code. Rate-limited to 5 per email per hour.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    # Always return 200 to prevent email enumeration
    if not user:
        return ApiResponse.ok(data={"message": "If the email exists, a new code has been sent."})

    # For verify_email, skip if already verified
    if req.purpose == "verify_email" and user.email_verified:
        return ApiResponse.ok(data={"message": "Email is already verified."})

    otp_code = await create_otp(db, email=req.email, purpose=req.purpose, user_id=user.id)
    if otp_code is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please try again later.",
        )

    await db.commit()
    background_tasks.add_task(send_otp_email, req.email, otp_code, req.purpose)

    return ApiResponse.ok(data={"message": "If the email exists, a new code has been sent."})


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate password reset — sends OTP to email.
    Always returns 200 to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()

    if user:
        otp_code = await create_otp(db, email=req.email, purpose="reset_password", user_id=user.id)
        await db.commit()  # Always commit so the OTP record is persisted
        if otp_code:
            background_tasks.add_task(send_otp_email, req.email, otp_code, "reset_password")
        else:
            logger.warning("Password reset OTP rate-limited for %s", req.email)
    else:
        logger.info("Password reset requested for non-existent email: %s", req.email)

    # Always return success to prevent email enumeration
    return ApiResponse.ok(
        data={"message": "If an account with that email exists, a reset code has been sent."}
    )


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """
    Reset password using OTP code. Validates OTP and updates the password.
    """
    # Find user
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    # Verify OTP
    is_valid = await verify_otp(db, email=req.email, code=req.code, purpose="reset_password")
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset code",
        )

    # Update password
    user.password_hash = hash_password(req.new_password)
    
    # If they successfully reset their password via email OTP, their email is verified!
    if not user.email_verified:
        user.email_verified = True
        
    await db.commit()

    return ApiResponse.ok(
        data={"message": "Password has been reset successfully. Please log in with your new password."}
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



@router.post("/login/phone/request")
async def login_phone_request(req: PhoneLoginRequest, db: AsyncSession = Depends(get_db)):
    """Generate and send OTP for phone login."""
    # Clean up old OTPs for this phone
    await db.execute(delete(OTP).where(OTP.identifier == req.phone, OTP.purpose == "login"))
    
    otp_code = str(random.randint(100000, 999999))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    otp_entry = OTP(
        identifier=req.phone,
        otp_code=otp_code,
        purpose="login",
        expires_at=expires_at
    )
    db.add(otp_entry)
    await db.flush()
    
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
    
    if account_sid and auth_token and twilio_number:
        try:
            client = Client(account_sid, auth_token)
            message = client.messages.create(
                body=f"Your Bank Statement Admin OTP is: {otp_code}. It expires in 5 minutes.",
                from_=twilio_number,
                to=req.phone
            )
            print(f"Twilio SMS sent successfully. Message SID: {message.sid}")
        except Exception as e:
            print(f"Failed to send Twilio SMS: {e}")
            raise HTTPException(status_code=500, detail="Failed to send SMS via Twilio. Check your credentials and phone number.")
    else:
        print(f"\n[DEV MOCK SMS] Twilio keys missing. OTP for {req.phone} is: {otp_code}\n")
    
    return ApiResponse.ok(message="OTP sent successfully")


@router.post("/login/phone/verify")
async def login_phone_verify(req: PhoneLoginVerifyRequest, db: AsyncSession = Depends(get_db)):
    """Verify OTP and return auth tokens."""
    result = await db.execute(
        select(OTP).where(
            OTP.identifier == req.phone,
            OTP.purpose == "login",
            OTP.otp_code == req.otp
        )
    )
    otp_entry = result.scalar_one_or_none()
    
    if not otp_entry:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP")
        
    if otp_entry.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await db.execute(delete(OTP).where(OTP.id == otp_entry.id))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="OTP expired")
        
    # Valid OTP. Delete it.
    await db.execute(delete(OTP).where(OTP.id == otp_entry.id))
    
    # Find user by phone
    user_result = await db.execute(select(User).where(User.phone == req.phone))
    user = user_result.scalar_one_or_none()
    
    if not user:
        # User requested to auto-create account if phone doesn't exist
        print(f"User with phone {req.phone} not found, auto-creating...")
        
        # We need a random email to bypass the non-null unique constraint on email
        random_email = f"phone_{req.phone.replace('+', '')}_{random.randint(1000,9999)}@placeholder.com"
        
        user = User(
            email=random_email,
            phone=req.phone,
            password_hash=hash_password(str(random.randint(10000000, 99999999))), # Random placeholder password
            full_name=f"User {req.phone}",
            email_verified=True  # Phone OTP login counts as identity verification
        )
        db.add(user)
        await db.flush()
        
        # Create a default firm for them
        firm = Firm(name=f"Firm {req.phone}")
        db.add(firm)
        await db.flush()
        
        membership = FirmMember(
            firm_id=firm.id,
            user_id=user.id,
            role="owner",
        )
        db.add(membership)
        await db.flush()
    else:
        # Existing phone users who log in via OTP are also considered verified
        if not user.email_verified:
            user.email_verified = True
    
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
                "phone": user.phone,
            },
            "tokens": TokenResponse(
                access_token=access_token,
                refresh_token=refresh_token,
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

