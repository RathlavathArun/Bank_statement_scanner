"""Tests for transaction CRUD endpoints."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from decimal import Decimal
from datetime import date

from db.models import Statement, Transaction, Client, Firm, LedgerMapping, LLMCache, LLMUsage
from db.database import get_db


@pytest_asyncio.fixture
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
async def test_confirmed_ledger_update_teaches_mapping(client: AsyncClient, seeded_statement, db: AsyncSession):
    """Confirmed ledger edits are saved as reusable ledger mappings."""
    tx = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id,
            Transaction.narration == "UPI SWIGGY",
        )
    )).scalars().one()

    response = await client.put(
        f"/v1/statements/{seeded_statement.id}/transactions/{tx.id}",
        json={"confirmed_ledger": "Meals and Entertainment"},
    )

    assert response.status_code == 200
    mapping = (await db.execute(
        __import__("sqlalchemy").select(LedgerMapping).where(
            LedgerMapping.client_id == seeded_statement.client_id,
            LedgerMapping.pattern == "upi swiggy",
        )
    )).scalars().one()
    assert mapping.ledger_name == "Meals and Entertainment"
    assert mapping.hit_count == 1


@pytest.mark.asyncio
async def test_ledger_suggestions_use_learned_mapping(client: AsyncClient, seeded_statement, db: AsyncSession):
    """Suggestion endpoint returns similar learned mappings for the same client."""
    txs = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id,
        )
    )).scalars().all()

    await client.put(
        f"/v1/statements/{seeded_statement.id}/transactions/{txs[0].id}",
        json={"confirmed_ledger": "Food Delivery"},
    )

    response = await client.get(
        f"/v1/statements/{seeded_statement.id}/transactions/{txs[0].id}/ledger-suggestions"
    )

    assert response.status_code == 200
    suggestions = response.json()["data"]["suggestions"]
    assert suggestions[0]["ledger_name"] == "Food Delivery"
    assert suggestions[0]["source"] == "db"


@pytest.mark.asyncio
async def test_enrich_transactions_adds_ai_fields(client: AsyncClient, seeded_statement, db: AsyncSession):
    """POST enrich fills cleaned narration, mode, counterparty, ledger and confidence."""
    response = await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/enrich",
        json={"only_missing": True, "limit": 10},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["updated"] == 5
    first = data["items"][0]
    assert first["narration_clean"]
    assert first["payment_mode"] == "UPI"
    assert first["suggested_ledger"] == "Food Expenses"
    assert Decimal(first["confidence"]) > Decimal("0.5")
    assert first["cache_status"] == "FALLBACK"
    assert data["usage"]["fallback_calls"] == 5

    tx = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id,
            Transaction.narration == "UPI SWIGGY",
        )
    )).scalars().one()
    assert tx.narration_clean is not None
    assert tx.payment_mode == "UPI"
    assert tx.confidence is not None


@pytest.mark.asyncio
async def test_enrich_transactions_respects_transaction_ids(client: AsyncClient, seeded_statement, db: AsyncSession):
    """Enrichment can target a caller-selected batch."""
    tx = (await db.execute(
        __import__("sqlalchemy").select(Transaction).where(
            Transaction.statement_id == seeded_statement.id,
            Transaction.narration == "Amazon Purchase",
        )
    )).scalars().one()

    response = await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/enrich",
        json={"transaction_ids": [tx.id], "only_missing": False},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["updated"] == 1
    assert data["items"][0]["transaction_id"] == tx.id
    assert data["items"][0]["suggested_ledger"] == "Online Purchases"


@pytest.mark.asyncio
async def test_enrich_transactions_uses_content_hash_cache(client: AsyncClient, seeded_statement, db: AsyncSession):
    """Repeated enrichment uses cached results and records zero-cost cache hits."""
    response = await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/enrich",
        json={"only_missing": False, "limit": 5},
    )
    assert response.status_code == 200
    assert response.json()["data"]["usage"]["fallback_calls"] == 5

    response = await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/enrich",
        json={"only_missing": False, "limit": 5},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["usage"]["cache_hits"] == 5
    assert data["items"][0]["cache_status"] == "HIT"

    cache_count = (await db.execute(
        __import__("sqlalchemy").select(__import__("sqlalchemy").func.count(LLMCache.id))
    )).scalar_one()
    usage_count = (await db.execute(
        __import__("sqlalchemy").select(__import__("sqlalchemy").func.count(LLMUsage.id))
    )).scalar_one()
    assert cache_count == 5
    assert usage_count == 10


@pytest.mark.asyncio
async def test_llm_usage_endpoint_returns_statement_totals(client: AsyncClient, seeded_statement, db: AsyncSession):
    """Usage endpoint exposes cache and cost totals for QA dashboards."""
    await client.post(
        f"/v1/statements/{seeded_statement.id}/transactions/enrich",
        json={"only_missing": False, "limit": 2},
    )

    response = await client.get(f"/v1/statements/{seeded_statement.id}/llm-usage")

    assert response.status_code == 200
    usage = response.json()["data"]["usage"]
    assert usage["calls"] == 2
    assert usage["fallback_calls"] == 2
    assert usage["cost_usd"] == "0.000000"


@pytest.mark.asyncio
async def test_parser_enrichment_pipeline_handles_large_batch(client: AsyncClient, db: AsyncSession):
    """Load-style parser + enrichment test for a larger statement batch."""
    firm = Firm(name="Load Firm")
    db.add(firm)
    await db.flush()
    client_record = Client(firm_id=firm.id, name="Load Client")
    db.add(client_record)
    await db.flush()
    statement = Statement(
        client_id=client_record.id,
        file_url="/tmp/load.csv",
        file_type="csv",
        bank_code="hdfc",
        status="READY_FOR_REVIEW",
    )
    db.add(statement)
    await db.flush()

    db.add_all(
        [
            Transaction(
                statement_id=statement.id,
                row_number=index,
                txn_date=date(2024, 2, 1),
                narration=f"UPI SWIGGY ORDER {index:04d}",
                debit=Decimal("250.00"),
                balance=Decimal("10000.00") - Decimal(index),
            )
            for index in range(1, 121)
        ]
    )
    await db.commit()

    response = await client.post(
        f"/v1/statements/{statement.id}/transactions/enrich",
        json={"only_missing": True, "limit": 120},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["updated"] == 120
    assert data["usage"]["fallback_calls"] == 120
    assert data["items"][0]["payment_mode"] == "UPI"


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
