"""
TOTP (Time-based One-Time Password) helpers — RFC 6238 / Google Authenticator
compatible.

Secrets are stored in the DB Fernet-encrypted using TOTP_ENCRYPTION_KEY from
settings. This ensures that even a DB dump cannot be used to clone TOTP devices.

PRD reference: Phase 1 Task 8 — "Add TOTP (authenticator app) MFA for admin
and owner roles. Twilio SMS OTP alone is SIM-swap vulnerable."
"""
from __future__ import annotations

import base64
import io
import logging
from typing import Optional

import pyotp
import qrcode
import qrcode.image.svg

from core.config import settings

logger = logging.getLogger(__name__)

# Issuer shown in authenticator apps (e.g. "Bank Statement Scanner")
TOTP_ISSUER = "Bank Statement Scanner"


# ─── Encryption helpers ──────────────────────────────────────────────────────

def _fernet():
    """Return a Fernet instance configured with TOTP_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet, InvalidToken  # noqa: F401

    key = settings.TOTP_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "TOTP_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext_secret: str) -> str:
    """Encrypt the TOTP secret for storage in the DB."""
    f = _fernet()
    return f.encrypt(plaintext_secret.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    """Decrypt the stored TOTP secret."""
    f = _fernet()
    return f.decrypt(ciphertext.encode()).decode()


# ─── TOTP operations ─────────────────────────────────────────────────────────

def generate_totp_secret() -> str:
    """Generate a fresh cryptographically random TOTP secret (base32)."""
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    """
    Return the otpauth:// URI suitable for QR code encoding.
    Most authenticator apps (Google Authenticator, Authy, 1Password) accept this.
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=email,
        issuer_name=TOTP_ISSUER,
    )


def verify_totp_code(secret: str, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the given secret.
    Allows a ±1 time-step window (30s each) for clock skew.
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)


def generate_qr_code_data_url(totp_uri: str) -> str:
    """
    Generate a QR code for the provisioning URI and return it as a
    data:image/png;base64,... string for embedding directly in HTML/JSON.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(totp_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"
