"""
Application configuration — reads from environment variables / .env file.
"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List
import os


class Settings(BaseSettings):
    # ─── Database ────────────────────────────────
    # PostgreSQL 16 (asyncpg driver). SQLite is NOT supported in production.
    # For local dev: run `docker-compose up postgres` first.
    DATABASE_URL: str = "postgresql+asyncpg://bse_admin:bse_secret_2026@localhost:5432/bank_statements"

    # ─── Redis ───────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # Vector memory / Qdrant
    QDRANT_ENABLED: bool = False
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION: str = "ledger_mappings"
    QDRANT_VECTOR_SIZE: int = 64

    # Claude / Anthropic narration enrichment
    ANTHROPIC_API_KEY: str | None = None
    ANTHROPIC_MODEL: str = "claude-3-5-haiku-latest"
    LLM_BATCH_SIZE: int = 20
    ANTHROPIC_INPUT_USD_PER_1M: float = 0.80
    ANTHROPIC_OUTPUT_USD_PER_1M: float = 4.00

    # ─── S3 / MinIO ─────────────────────────────
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET: str = "bank-statements"

    # ─── OCR Engine ─────────────────────────────
    # "textract" = always use AWS Textract (errors if no creds)
    # "tesseract" = always use local Tesseract
    # "auto" = try Textract first, fall back to Tesseract
    OCR_ENGINE: str = "auto"
    TEXTRACT_REGION: str = "ap-south-1"
    TEXTRACT_S3_BUCKET: str = ""           # bucket for async jobs; defaults to S3_BUCKET if blank
    TEXTRACT_ASYNC_ENABLED: bool = False   # True = use start_document_analysis (S3 flow)
    TEXTRACT_FEATURE_TYPES: str = "TABLES" # comma-separated: TABLES,FORMS
    AWS_ACCESS_KEY_ID: str | None = None                      # ✅ Falls back to IAM role
    AWS_SECRET_ACCESS_KEY: str | None = None           
    AWS_DEFAULT_REGION: str = "ap-south-1"

    # ─── JWT ─────────────────────────────────────
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── Email / OTP ────────────────────────────
    EMAIL_PROVIDER: str = "smtp"  # "smtp" | "ses"
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""  # Gmail App Password
    SMTP_FROM_EMAIL: str = ""  # Set via env var — must match a verified SES identity in production
    SMTP_FROM_NAME: str = "Bank Statement Scanner"
    OTP_EXPIRY_MINUTES: int = 10
    OTP_MAX_ATTEMPTS_PER_HOUR: int = 5

    # ─── ClamAV (virus scanning) ─────────────────
    CLAMAV_ENABLED: bool = True
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310

    # ─── TOTP MFA ────────────────────────────────
    # 32-byte Fernet key (url-safe base64). Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    TOTP_ENCRYPTION_KEY: str = ""

    # ─── App ─────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
