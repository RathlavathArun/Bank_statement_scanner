"""Tests for transaction CRUD endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from datetime import date

from db.models import Statement, Transaction, Client, Firm
from db.database import get_db


@pytest.fixture
async def seeded_statement(db: AsyncSession):
    """Create a test statement with 5 transactions."""
    # Create firm and client
    firm = Firm(name="Test Firm")
    db.add(firm)
    await db.flush()

    client = Client(firm_id=firm.id, name="Test Client")
    db.add(client)
    await db.flush()

    # Create statement
    statement = Statement(
        client_id=client.id,
        file_url="/tmp/test.csv",
        file_type="csv",
        bank_code="hdfc",
        status="READY_FOR_REVIEW",
    )
    db.add(statement)
    await db.flush()

    # Add 5 transactions alternating DEBIT/CREDIT
    transactions = [
        Transaction(
            statement_id=statement.id,
            row_number=1,
            txn_date=date(2024, 1, 1),
            narration="UPI SWIGGY",
            debit=Decimal("350.00"),
            balance=Decimal("49650.00"),
        ),
        Transaction(
            statement_id=statement.id,
            row_number=2,
            txn_date=date(2024, 1, 2),
            narration="Salary Credit",
            credit=Decimal("50000.00"),
            balance=Decimal("99650.00"),
        ),
        Transaction(
            statement_id=statement.id,
            row_number=3,
            txn_date=date(2024, 1, 3),
            narration="Amazon Purchase",
            debit=Decimal("1299.00"),
            balance=Decimal("98351.00"),
        ),
        Transaction(
            statement_id=statement.id,
            row_number=4,
            txn_date=date(2024, 1, 4),
            narration="ATM Withdrawal",
            debit=Decimal("5000.00"),
            balance=Decimal("93351.00"),
        ),
        Transaction(
            statement_id=statement.id,
            row_number=5,
            txn_date=date(2024, 1, 5),
            narration="Transfer IN",
            credit=Decimal("2000.00"),
            balance=Decimal("95351.00"),
        ),
    ]
    db.add_all(transactions)
    await db.commit()

    return statement


@pytest.mark.asyncio
async def test_list_statements(client: AsyncClient, db: AsyncSession):
    """GET /v1/statements returns paginated list."""
    response = await client.get("/v1/statements")
    assert response.status_code == 200
    data = response.json()
    assert data["success"]
    assert "data" in data
    assert "items" in data["data"]


@pytest.mark.asyncio
async def test_list_statements_pagination(client: AsyncClient, seeded_statement, db: AsyncSession):
    """GET /v1/statements with page and size parameters."""
    response = await client.get("/v1/statements?page=1&size=1")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["page"] == 1
    assert data["data"]["size"] == 1
    assert len(data["data"]["items"]) <= 1


@pytest.mark.asyncio
async def test_list_transactions(client: AsyncClient, seeded_statement, db: AsyncSession):
    """GET /v1/statements/{id}/transactions returns transactions."""
    response = await client.get(f"/v1/statements/{seeded_statement.id}/transactions")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["items"]) == 5


@pytest.mark.asyncio
async def test_filter_transactions_by_debit(client: AsyncClient, seeded_statement, db: AsyncSession):
    """GET /v1/statements/{id}/transactions?tx_type=DEBIT."""
    response = await client.get(
        f"/v1/statements/{seeded_statement.id}/transactions?tx_type=DEBIT"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["items"]) == 3  # 3 debit transactions


@pytest.mark.asyncio
async def test_filter_transactions_by_credit(client: AsyncClient, seeded_statement, db: AsyncSession):
    """GET /v1/statements/{id}/transactions?tx_type=CREDIT."""
    response = await client.get(
        f"/v1/statements/{seeded_statement.id}/transactions?tx_type=CREDIT"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["items"]) == 2  # 2 credit transactions


@pytest.mark.asyncio
async def test_search_narration(client: AsyncClient, seeded_statement, db: AsyncSession):
    """GET /v1/statements/{id}/transactions?search=Salary."""
    response = await client.get(
        f"/v1/statements/{seeded_statement.id}/transactions?search=Salary"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["items"]) == 1


@pytest.mark.asyncio
async def test_update_transaction_narration(client: AsyncClient, seeded_statement, db: AsyncSession):
    """PUT /v1/statements/{id}/transactions/{tx_id} updates narration."""
    tx_id = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id
        )
    )).scalars().first().id

    response = await client.put(
        f"/v1/statements/{seeded_statement.id}/transactions/{tx_id}",
        json={"narration": "Updated Narration"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["narration"] == "Updated Narration"


@pytest.mark.asyncio
async def test_update_wrong_statement_404(client: AsyncClient, seeded_statement, db: AsyncSession):
    """PUT with wrong statement_id returns 404."""
    response = await client.put(
        f"/v1/statements/nonexistent/transactions/nonexistent",
        json={"narration": "Test"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_update_transactions(client: AsyncClient, seeded_statement, db: AsyncSession):
    """POST /v1/statements/{id}/transactions/bulk-update."""
    txs = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id
        ).limit(2)
    )).scalars().all()

    response = await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/bulk-update",
        json={
            "updates": [
                {"id": txs[0].id, "confirmed_ledger": "Expense"},
                {"id": txs[1].id, "confirmed_ledger": "Income"},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["updated"] == 2


@pytest.mark.asyncio
async def test_mark_reviewed(client: AsyncClient, seeded_statement, db: AsyncSession):
    """PATCH /v1/statements/{id}/status."""
    response = await client.patch(
        f"/v1/statements/{seeded_statement.id}/status",
        json={"status": "REVIEWED"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["status"] == "REVIEWED"


@pytest.mark.asyncio
async def test_invalid_status_400(client: AsyncClient, seeded_statement, db: AsyncSession):
    """PATCH with invalid status returns 400."""
    response = await client.patch(
        f"/v1/statements/{seeded_statement.id}/status",
        json={"status": "INVALID"},
    )
    assert response.status_code == 400
