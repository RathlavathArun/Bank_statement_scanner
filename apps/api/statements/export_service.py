"""Shared export generation service for API routes and Celery workers."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.observability import get_tracer
from db.models import Statement, Transaction
from statements.exporters import generate_csv, generate_excel, generate_json, generate_tally_xml

tracer = get_tracer("bank-statement-scanner")

EXPORTS_DIR = Path(__file__).resolve().parents[1] / "exports"
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
EXPORT_TTL_HOURS = 24
DOWNLOAD_TOKEN_TTL_MINUTES = 15
READY_STATUSES = {"READY_FOR_REVIEW", "REVIEWED", "EXPORTED"}
FORMAT_EXT = {"tally_xml": "xml", "csv": "csv", "excel": "xlsx", "json": "json"}
FORMAT_CONTENT_TYPE = {
    "tally_xml": "application/xml",
    "csv": "text/csv",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_filename(stmt: Statement | None, fmt: str) -> str:
    ext = FORMAT_EXT.get(fmt, "bin")
    bank = getattr(stmt, "bank_code", None) or "bank"
    stamp = utcnow().strftime("%Y-%m-%d")
    return f"{bank}_{stamp}_{fmt}.{ext}"


def statement_meta(stmt: Statement) -> dict[str, Any]:
    return {
        "id": stmt.id,
        "filename": stmt.metadata_.get("original_filename") or Path(stmt.file_url).name or "statement",
        "bank_id": stmt.bank_code or "Unknown",
        "file_type": stmt.file_type,
        "status": stmt.status,
    }


def serialize_export_transaction(tx: Transaction) -> dict[str, Any]:
    amount = tx.debit if tx.debit is not None else tx.credit
    tx_type = "DEBIT" if tx.debit is not None else "CREDIT"
    return {
        "id": tx.id,
        "statement_id": tx.statement_id,
        "date": tx.txn_date.isoformat() if tx.txn_date else None,
        "value_date": tx.value_date.isoformat() if tx.value_date else None,
        "narration": tx.narration,
        "reference_no": tx.reference_no,
        "amount": amount,
        "tx_type": tx_type,
        "balance": tx.balance,
        "payment_mode": tx.payment_mode,
        "counterparty": tx.counterparty,
        "ledger_name": tx.confirmed_ledger or tx.suggested_ledger,
        "ocr_confidence": tx.ocr_confidence,
        "page_number": tx.page_number,
        "is_reviewed": bool(tx.confirmed_ledger) and not tx.is_ignored,
        "is_ignored": tx.is_ignored,
        "created_at": tx.created_at,
    }


async def load_transactions(db: AsyncSession, statement_id: str) -> list[Transaction]:
    result = await db.execute(
        select(Transaction)
        .where(
            Transaction.statement_id == statement_id,
            Transaction.is_ignored.is_(False)
        )
        .order_by(Transaction.row_number)
    )
    return list(result.scalars().all())


async def build_export_content(
    db: AsyncSession,
    stmt: Statement,
    fmt: str,
    company_name: str | None = None,
    bank_ledger_name: str | None = None,
    strict_reviewed_only: bool = False,
) -> tuple[bytes, int]:
    with tracer.start_as_current_span("export_content") as span:
        span.set_attribute("statement_id", stmt.id)
        span.set_attribute("format", fmt)
        transactions = [serialize_export_transaction(tx) for tx in await load_transactions(db, stmt.id)]
        meta = statement_meta(stmt)

        if fmt == "tally_xml":
            content: bytes | str = generate_tally_xml(
                transactions,
                company_name=company_name or "My Company",
                bank_ledger_name=bank_ledger_name or "Bank Account",
                strict_reviewed_only=strict_reviewed_only,
            )
        elif fmt == "csv":
            content = generate_csv(transactions)
        elif fmt == "excel":
            content = generate_excel(transactions, meta)
        elif fmt == "json":
            content = generate_json(transactions, meta)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown format: {fmt}")

        payload = content if isinstance(content, bytes) else content.encode("utf-8")
        span.set_attribute("transaction_count", len(transactions))
        return payload, len(transactions)


def write_export_file(statement_id: str, job_id: str, fmt: str, payload: bytes) -> Path:
    export_dir = EXPORTS_DIR / statement_id
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"{job_id}.{FORMAT_EXT[fmt]}"
    file_path.write_bytes(payload)
    return file_path
