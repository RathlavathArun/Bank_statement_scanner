from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Client, ExportJob, Firm, Statement, Transaction


@pytest_asyncio.fixture
async def exportable_statement(db: AsyncSession):
    firm = Firm(name="Export Firm")
    db.add(firm)
    await db.flush()

    client = Client(firm_id=firm.id, name="Export Client")
    db.add(client)
    await db.flush()

    statement = Statement(
        client_id=client.id,
        file_url="/tmp/exportable.csv",
        file_type="csv",
        bank_code="hdfc",
        status="READY_FOR_REVIEW",
        metadata_={"original_filename": "exportable.csv"},
    )
    db.add(statement)
    await db.flush()

    db.add_all(
        [
            Transaction(
                statement_id=statement.id,
                row_number=1,
                txn_date=date(2024, 1, 1),
                narration="UPI SWIGGY",
                debit=Decimal("350.00"),
                balance=Decimal("49650.00"),
                payment_mode="UPI",
                counterparty="Swiggy",
                confirmed_ledger="Food Expenses",
                ocr_confidence=Decimal("0.650"),
            ),
            Transaction(
                statement_id=statement.id,
                row_number=2,
                txn_date=date(2024, 1, 2),
                narration="Salary Credit",
                credit=Decimal("50000.00"),
                balance=Decimal("99650.00"),
                payment_mode="NEFT",
                counterparty="Employer",
                suggested_ledger="Salary Income",
                ocr_confidence=Decimal("0.940"),
            ),
        ]
    )
    await db.commit()
    return statement


@pytest.mark.asyncio
async def test_create_csv_export_updates_statement_and_returns_download(client: AsyncClient, db: AsyncSession, exportable_statement: Statement):
    response = await client.post(
        f"/v1/statements/{exportable_statement.id}/export",
        json={"format": "csv"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["format"] == "csv"
    assert payload["status"] == "READY"
    assert payload["download_url"].endswith("/download")
    assert payload["transaction_count"] == 2
    assert payload["idempotent"] is False

    statement = await db.get(Statement, exportable_statement.id)
    assert statement.status == "EXPORTED"

    job = await db.get(ExportJob, payload["export_id"])
    assert job is not None
    assert job.file_path and Path(job.file_path).exists()


@pytest.mark.asyncio
async def test_export_is_idempotent_for_unexpired_ready_job(client: AsyncClient, exportable_statement: Statement):
    first = await client.post(
        f"/v1/statements/{exportable_statement.id}/export",
        json={"format": "json"},
    )
    second = await client.post(
        f"/v1/statements/{exportable_statement.id}/export",
        json={"format": "json"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["export_id"] == first.json()["export_id"]
    assert second.json()["idempotent"] is True


@pytest.mark.asyncio
async def test_export_requires_statement_ready_state(client: AsyncClient, db: AsyncSession):
    firm = Firm(name="Blocked Firm")
    db.add(firm)
    await db.flush()
    client_record = Client(firm_id=firm.id, name="Blocked Client")
    db.add(client_record)
    await db.flush()
    statement = Statement(
        client_id=client_record.id,
        file_url="/tmp/blocked.csv",
        file_type="csv",
        bank_code="hdfc",
        status="PARSING",
    )
    db.add(statement)
    await db.commit()

    response = await client.post(f"/v1/statements/{statement.id}/export", json={"format": "csv"})

    assert response.status_code == 409
    assert "not ready for export" in response.json()["detail"]


@pytest.mark.asyncio
async def test_list_download_and_delete_export(client: AsyncClient, db: AsyncSession, exportable_statement: Statement):
    created = await client.post(
        f"/v1/statements/{exportable_statement.id}/export",
        json={"format": "tally_xml", "company_name": "Acme Pvt Ltd", "bank_ledger_name": "HDFC Bank A/c"},
    )
    export_id = created.json()["export_id"]

    list_response = await client.get(f"/v1/statements/{exportable_statement.id}/exports")
    assert list_response.status_code == 200
    assert list_response.json()[0]["export_id"] == export_id

    download_response = await client.get(f"/v1/exports/{export_id}/download")
    assert download_response.status_code == 200
    assert download_response.headers["content-type"].startswith("application/xml")
    assert "attachment;" in download_response.headers["content-disposition"]

    file_path = Path((await db.get(ExportJob, export_id)).file_path)
    delete_response = await client.delete(f"/v1/exports/{export_id}")
    assert delete_response.status_code == 204
    assert not file_path.exists()
    assert await db.get(ExportJob, export_id) is None


@pytest.mark.asyncio
async def test_download_rejects_expired_exports(client: AsyncClient, db: AsyncSession, exportable_statement: Statement):
    created = await client.post(
        f"/v1/statements/{exportable_statement.id}/export",
        json={"format": "csv"},
    )
    export_id = created.json()["export_id"]

    job = await db.get(ExportJob, export_id)
    job.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    await db.commit()

    response = await client.get(f"/v1/exports/{export_id}/download")
    assert response.status_code == 410
