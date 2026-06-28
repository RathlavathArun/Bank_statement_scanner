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
    pool_pre_ping=True,  # reconnect silently on stale connections
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
    """Create all tables and apply Row-Level Security policies."""
    async with engine.begin() as conn:
        from db.models import (  # noqa: F401
            Firm, User, FirmMember, Client,
            Statement, Transaction, LedgerMapping, Ledger, AuditLog,
            LLMCache, LLMUsage, BankTemplate, OTP, ExportJob, OtpCode, PasswordResetToken
        )
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))

    # Apply Row-Level Security policies (idempotent — safe to call on every boot)
    try:
        from db.rls import apply_rls_policies
        async with engine.begin() as conn:
            await apply_rls_policies(conn)
    except Exception as e:  # noqa: BLE001
        # RLS setup is best-effort on first boot; will succeed on subsequent calls
        import logging
        logging.getLogger(__name__).warning("RLS policy setup skipped: %s", e)
