from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Client, ExportJob, Firm, FirmMember, LLMUsage, Statement, Transaction
from statements.processing import enrich_transactions_job, export_statement_job, process_statement_job


async def _firm_client(db: AsyncSession, auth_user):
    firm = Firm(name="Idempotency Firm")
    db.add(firm)
    await db.flush()
    db.add(FirmMember(firm_id=firm.id, user_id=auth_user.id, role="owner"))
    client = Client(firm_id=firm.id, name="Idempotency Client")
    db.add(client)
    await db.flush()
    return firm, client


@pytest.mark.asyncio
async def test_process_statement_retry_does_not_duplicate_transactions(db: AsyncSession, auth_user, tmp_path):
    firm, client = await _firm_client(db, auth_user)
    csv_path = tmp_path / "statement.csv"
    csv_path.write_text(
        "Date,Description,Debit,Credit,Balance\n"
        "2026-05-01,UPI Payment to Vendor,1200,,48800\n"
        "2026-05-03,NEFT Received,,10000,58800\n",
        encoding="utf-8",
    )
    statement = Statement(
        client_id=client.id,
        uploaded_by=auth_user.id,
        file_url=str(csv_path),
        file_type="csv",
        bank_code="hdfc",
        status="PARSING",
        metadata_={"original_filename": "statement.csv"},
    )
    db.add(statement)
    await db.commit()

    first = await process_statement_job(
        db,
        job_id="parse-retry-test",
        statement_id=statement.id,
        file_path=str(csv_path),
        bank="hdfc",
        password=None,
        firm_id=firm.id,
    )
    second = await process_statement_job(
        db,
        job_id="parse-retry-test",
        statement_id=statement.id,
        file_path=str(csv_path),
        bank="hdfc",
        password=None,
        firm_id=firm.id,
    )

    count = (await db.execute(
        select(func.count(Transaction.id)).where(Transaction.statement_id == statement.id)
    )).scalar_one()
    assert first["transactions"] == 2
    assert second["idempotent"] is True
    assert count == 2


@pytest.mark.asyncio
async def test_enrichment_retry_does_not_duplicate_llm_usage(db: AsyncSession, auth_user):
    firm, client = await _firm_client(db, auth_user)
    statement = Statement(
        client_id=client.id,
        uploaded_by=auth_user.id,
        file_url="/tmp/llm.csv",
        file_type="csv",
        bank_code="hdfc",
        status="READY_FOR_REVIEW",
    )
    db.add(statement)
    await db.flush()
    db.add(Transaction(
        statement_id=statement.id,
        row_number=1,
        txn_date=date(2026, 5, 1),
        narration="UPI SWIGGY",
        debit=Decimal("250.00"),
        balance=Decimal("1000.00"),
    ))
    await db.commit()

    first = await enrich_transactions_job(
        db,
        job_id="llm-retry-test",
        statement_id=statement.id,
        firm_id=firm.id,
        only_missing=False,
        limit=10,
        force=True,
    )
    usage_after_first = (await db.execute(
        select(func.count(LLMUsage.id)).where(LLMUsage.statement_id == statement.id)
    )).scalar_one()
    second = await enrich_transactions_job(
        db,
        job_id="llm-retry-test",
        statement_id=statement.id,
        firm_id=firm.id,
        only_missing=False,
        limit=10,
        force=True,
    )
    usage_after_second = (await db.execute(
        select(func.count(LLMUsage.id)).where(LLMUsage.statement_id == statement.id)
    )).scalar_one()

    assert first["updated"] == 1
    assert second["idempotent"] is True
    assert usage_after_first == 1
    assert usage_after_second == 1


@pytest.mark.asyncio
async def test_export_retry_reuses_existing_export_job_and_file(db: AsyncSession, auth_user, tmp_path):
    firm, client = await _firm_client(db, auth_user)
    statement = Statement(
        client_id=client.id,
        uploaded_by=auth_user.id,
        file_url=str(tmp_path / "export.csv"),
        file_type="csv",
        bank_code="hdfc",
        status="READY_FOR_REVIEW",
    )
    db.add(statement)
    await db.flush()
    db.add(Transaction(
        statement_id=statement.id,
        row_number=1,
        txn_date=date(2026, 5, 1),
        narration="NEFT Received",
        credit=Decimal("1000.00"),
        balance=Decimal("1000.00"),
    ))
    export = ExportJob(statement_id=statement.id, format="csv", status="PENDING")
    db.add(export)
    await db.commit()

    first = await export_statement_job(
        db,
        job_id="export-retry-test",
        export_id=export.id,
        statement_id=statement.id,
        firm_id=firm.id,
        fmt="csv",
        company_name=None,
        bank_ledger_name=None,
        strict_reviewed_only=False,
    )
    export_record = await db.get(ExportJob, export.id)
    file_path = export_record.file_path
    second = await export_statement_job(
        db,
        job_id="export-retry-test",
        export_id=export.id,
        statement_id=statement.id,
        firm_id=firm.id,
        fmt="csv",
        company_name=None,
        bank_ledger_name=None,
        strict_reviewed_only=False,
    )
    export_count = (await db.execute(
        select(func.count(ExportJob.id)).where(ExportJob.statement_id == statement.id)
    )).scalar_one()

    assert first["status"] == "READY"
    assert second["idempotent"] is True
    assert export_count == 1
    assert (await db.get(ExportJob, export.id)).file_path == file_path
