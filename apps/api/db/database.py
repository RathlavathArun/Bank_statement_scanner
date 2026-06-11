"""
SQLAlchemy async engine and session factory.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables and run lightweight schema updates."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        from db.models import (  # noqa: F401
            Firm, User, FirmMember, Client,
            Statement, Transaction, LedgerMapping, Ledger, AuditLog,
            LLMCache, LLMUsage, ExportJob, OtpCode, PasswordResetToken
        )
        await conn.run_sync(Base.metadata.create_all)
        
        # Lightweight migration to add email_verified if it doesn't exist
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN DEFAULT FALSE;"))
        except Exception as e:
            # SQLite might not support IF NOT EXISTS for columns in older versions, but Postgres does.
            # We catch it just in case.
            pass
