"""
Application configuration — reads from environment variables / .env file.
"""
from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # ─── Database ────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./bank_statements.db"

    # ─── Redis ───────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ─── S3 / MinIO ─────────────────────────────
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin123"
    S3_BUCKET: str = "bank-statements"

    # ─── JWT ─────────────────────────────────────
    JWT_SECRET_KEY: str = "super-secret-key-change-in-production-2026"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ─── App ─────────────────────────────────────
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    class Config:
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
