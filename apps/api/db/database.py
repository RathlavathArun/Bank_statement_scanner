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
    """Create all tables (used for development with SQLite)."""
    async with engine.begin() as conn:
        from db.models import (  # noqa: F401
            Firm, User, FirmMember, Client,
            Statement, Transaction, LedgerMapping, Ledger, AuditLog,
            LLMCache, LLMUsage, BankTemplate, OTP
        )
        await conn.run_sync(Base.metadata.create_all)
