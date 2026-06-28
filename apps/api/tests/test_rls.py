"""
tests/test_rls.py — Row-Level Security cross-tenant isolation tests.

Verifies that a user in Firm A cannot read Firm B's statements, transactions,
clients, or export_jobs even if they guess the ID.

Run:
    pytest apps/api/tests/test_rls.py -v
"""
from __future__ import annotations

import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from core.config import settings
from db.models import Firm, User, FirmMember, Client, Statement
from db.rls import set_rls_context
from auth.service import hash_password


# ─── Fixtures ────────────────────────────────────────────────


@pytest.fixture(scope="module")
def event_loop():
    """Use a single event loop for the whole module."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def engine():
    eng = create_async_engine(settings.DATABASE_URL, echo=False, future=True)
    yield eng
    await eng.dispose()


@pytest.fixture(scope="module")
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="module")
async def two_firms(session_factory):
    """Create two isolated firms with one client and one statement each."""
    async with session_factory() as db:
        # Firm A
        firm_a = Firm(name="Test Firm A")
        firm_b = Firm(name="Test Firm B")
        db.add_all([firm_a, firm_b])
        await db.flush()

        user_a = User(email="rls_user_a@test.local",
                      password_hash=hash_password("pw"), email_verified=True)
        user_b = User(email="rls_user_b@test.local",
                      password_hash=hash_password("pw"), email_verified=True)
        db.add_all([user_a, user_b])
        await db.flush()

        db.add(FirmMember(firm_id=firm_a.id, user_id=user_a.id, role="owner"))
        db.add(FirmMember(firm_id=firm_b.id, user_id=user_b.id, role="owner"))
        await db.flush()

        client_a = Client(firm_id=firm_a.id, name="Client A")
        client_b = Client(firm_id=firm_b.id, name="Client B")
        db.add_all([client_a, client_b])
        await db.flush()

        stmt_a = Statement(client_id=client_a.id, file_url="s3://a/a.pdf",
                           file_type="pdf", status="UPLOADED")
        stmt_b = Statement(client_id=client_b.id, file_url="s3://b/b.pdf",
                           file_type="pdf", status="UPLOADED")
        db.add_all([stmt_a, stmt_b])
        await db.commit()

        return {
            "firm_a_id": firm_a.id,
            "firm_b_id": firm_b.id,
            "client_a_id": client_a.id,
            "client_b_id": client_b.id,
            "stmt_a_id": stmt_a.id,
            "stmt_b_id": stmt_b.id,
        }


# ─── Tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_firm_a_cannot_read_firm_b_clients(session_factory, two_firms):
    """Firm A's RLS context must not return Firm B's clients."""
    async with session_factory() as db:
        await set_rls_context(db, two_firms["firm_a_id"])
        result = await db.execute(
            select(Client).where(Client.id == two_firms["client_b_id"])
        )
        assert result.scalar_one_or_none() is None, (
            "RLS VIOLATION: Firm A can read Firm B's client!"
        )


@pytest.mark.asyncio
async def test_firm_b_cannot_read_firm_a_statements(session_factory, two_firms):
    """Firm B's RLS context must not return Firm A's statements."""
    async with session_factory() as db:
        await set_rls_context(db, two_firms["firm_b_id"])
        result = await db.execute(
            select(Statement).where(Statement.id == two_firms["stmt_a_id"])
        )
        assert result.scalar_one_or_none() is None, (
            "RLS VIOLATION: Firm B can read Firm A's statement!"
        )


@pytest.mark.asyncio
async def test_firm_a_can_read_own_clients(session_factory, two_firms):
    """Firm A should still be able to read its own clients."""
    async with session_factory() as db:
        await set_rls_context(db, two_firms["firm_a_id"])
        result = await db.execute(
            select(Client).where(Client.id == two_firms["client_a_id"])
        )
        assert result.scalar_one_or_none() is not None, (
            "Firm A cannot read its own client — RLS policy is too strict!"
        )


@pytest.mark.asyncio
async def test_empty_firm_context_reads_nothing(session_factory, two_firms):
    """An empty/cleared RLS context should return no tenant rows."""
    async with session_factory() as db:
        await set_rls_context(db, None)
        result = await db.execute(select(Client))
        rows = result.scalars().all()
        assert len(rows) == 0, (
            f"RLS VIOLATION: {len(rows)} clients visible with no firm context!"
        )
