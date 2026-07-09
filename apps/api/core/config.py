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
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Vector memory / Qdrant
    QDRANT_ENABLED: bool = False
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION: str = "ledger_mappings"
    QDRANT_VECTOR_SIZE: int = 64

    # Claude / Anthropic narration enrichment
    ANTHROPIC_API_KEY: str | None = None
    # Task 15 — Primary model: Sonnet 4.5 for > 85% auto-categorisation accuracy
    # on complex NEFT/RTGS narrations (PRD Phase 3).
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"
    # Task 15 — Fallback model: Haiku is used when Sonnet is unavailable
    # (rate-limit, API outage, etc.). Lower accuracy but keeps enrichment live.
    ANTHROPIC_FALLBACK_MODEL: str = "claude-3-5-haiku-latest"
    LLM_BATCH_SIZE: int = 50            # Task 16: 50 txns/call (was 20)
    LLM_MAX_CONCURRENT_BATCHES: int = 4  # Task 16: max 4 parallel API calls
    ANTHROPIC_INPUT_USD_PER_1M: float = 3.00   # Sonnet 4.5 pricing
    ANTHROPIC_OUTPUT_USD_PER_1M: float = 15.00  # Sonnet 4.5 pricing

    # Task 18 — GPT-4o-mini as 3rd-tier fallback when both Anthropic models fail.
    # PRD risk §14: Anthropic outage must not halt all categorisation.
    OPENAI_API_KEY: str | None = None
    OPENAI_FALLBACK_MODEL: str = "gpt-4o-mini"
    OPENAI_INPUT_USD_PER_1M: float = 0.15    # GPT-4o-mini pricing (input)
    OPENAI_OUTPUT_USD_PER_1M: float = 0.60   # GPT-4o-mini pricing (output)
    # Zero Data Retention — set to True only AFTER signing the Anthropic ZDR
    # agreement at https://console.anthropic.com/settings/privacy
    # When enabled, the `anthropic-beta: zero-data-retention-2024-02-23` header
    # is attached to every API call so Anthropic does not retain prompt/response
    # data. PRD Task 14 — required before PII-masked data flows to the API.
    ANTHROPIC_ZDR_ENABLED: bool = False
    ANTHROPIC_ZERO_DATA_RETENTION: bool = True

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

    # ─── Observability (Phase 2) ────────────────
    SENTRY_DSN: str | None = None
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None
    OTEL_SERVICE_NAME: str = "bank-statement-scanner"
    ENVIRONMENT: str = "production"

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

    @property
    def celery_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def celery_result_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
