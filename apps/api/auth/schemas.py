"""
Pydantic schemas for authentication requests and responses.
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional
from datetime import datetime


# ─── Request Schemas ─────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(None, max_length=15)
    firm_name: str = Field(..., min_length=1, max_length=255, description="Name of the firm to create")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., max_length=15)


class PhoneLoginVerifyRequest(BaseModel):
    phone: str = Field(..., max_length=15)
    otp: str = Field(..., min_length=6, max_length=10)

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)


class ResendOtpRequest(BaseModel):
    email: EmailStr
    purpose: Literal["verify_email", "reset_password"] = "verify_email"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: Optional[str] = Field(None, min_length=6, max_length=10)
    code: Optional[str] = Field(None, min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)
# ─── Response Schemas ────────────────────────────────────────
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    phone: Optional[str]
    email_verified: bool
    firm: Optional[dict] = None
    created_at: datetime

    class Config:
        from_attributes = True
