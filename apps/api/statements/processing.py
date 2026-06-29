"""Async processing services shared by API routes and Celery tasks."""
from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.job_progress import update_job_progress
from core.observability import get_tracer
from db.models import ExportJob, LLMCache, Statement, Transaction
from db.rls import set_rls_context
from statements.export_service import EXPORT_TTL_HOURS, build_export_content, utcnow, write_export_file
from statements.llm_enrichment import apply_enrichment, enrich_transactions_with_tracking, serialize_enrichment
from statements.llm_tracking import content_hash_for_transaction, serialize_usage, summarize_usage
from statements.parser import PDFReadError, PasswordProtectedError, StatementParserError, parse_statement
from statements.websocket import notify_status_change

logger = logging.getLogger(__name__)
tracer = get_tracer("bank-statement-scanner")


def _parse_statement_func():
    try:
        from statements import router as router_module

        return getattr(router_module, "parse_statement", parse_statement)
    except Exception:  # noqa: BLE001
        return parse_statement


def _job_metadata(
    metadata: dict,
    job_type: str,
    *,
    job_id: str,
    status: str,
    stage: str,
    progress: int,
    detail: str | None = None,
) -> dict:
    jobs = dict((metadata or {}).get("jobs") or {})
    jobs[job_type] = {
        "job_id": job_id,
        "status": status,
        "stage": stage,
        "progress": progress,
        "detail": detail,
    }
    return {**(metadata or {}), "jobs": jobs}


async def _set_statement_job(
    db: AsyncSession,
    statement: Statement,
    job_type: str,
    *,
    job_id: str,
    status: str,
    stage: str,
    progress: int,
    detail: str | None = None,
) -> None:
    statement.metadata_ = _job_metadata(
        statement.metadata_,
        job_type,
        job_id=job_id,
        status=status,
        stage=stage,
        progress=progress,
        detail=detail,
    )
    await db.flush()


async def process_statement_job(
    db: AsyncSession,
    *,
    job_id: str,
    statement_id: str,
    file_path: str,
    bank: str | None,
    password: str | None,
    firm_id: str,
) -> dict:
    await set_rls_context(db, firm_id)
    statement = await db.get(Statement, statement_id)
    if not statement:
        update_job_progress(job_id, job_type="parse", status="FAILED", stage="missing", progress=100)
        return {"statement_id": statement_id, "status": "missing"}

    existing_tx_ids = await _transaction_ids(db, statement.id)
    if existing_tx_ids:
        if statement.status in {"UPLOADED", "PARSING", "OCR"}:
            statement.status = "READY_FOR_REVIEW"
        await _set_statement_job(
            db,
            statement,
            "parse",
            job_id=job_id,
            status="COMPLETED",
            stage="ready",
            progress=100,
            detail="Existing parsed transactions reused for idempotent retry.",
        )
        await db.commit()
        update_job_progress(
            job_id,
            job_type="parse",
            status="COMPLETED",
            stage="ready",
            progress=100,
            statement_id=statement.id,
            detail="Existing parsed transactions reused for idempotent retry.",
            extra={"transactions": len(existing_tx_ids), "idempotent": True},
        )
        await notify_status_change(statement.id, statement.status)
        await _auto_enrich_missing(db, job_id, statement.id, firm_id, existing_tx_ids)
        return {"statement_id": statement.id, "status": statement.status, "transactions": len(existing_tx_ids), "idempotent": True}

    await _set_statement_job(db, statement, "parse", job_id=job_id, status="STARTED", stage="parser", progress=10)
    update_job_progress(job_id, job_type="parse", status="STARTED", stage="parser", progress=10, statement_id=statement_id)
    await db.commit()

    def on_ocr_progress(page_current: int, page_total: int) -> None:
        progress = 20 + int((page_current / max(page_total, 1)) * 55)
        update_job_progress(
            job_id,
            job_type="parse",
            status="STARTED",
            stage="ocr",
            progress=progress,
            statement_id=statement_id,
            extra={"page_current": page_current, "page_total": page_total},
        )

    try:
        with tracer.start_as_current_span("parse_statement") as span:
            span.set_attribute("statement_id", statement_id)
            span.set_attribute("file_path", file_path)
            try:
                parsed = _parse_statement_func()(Path(file_path), bank, password=password, on_ocr_progress=on_ocr_progress)
            except TypeError as exc:
                if "on_ocr_progress" not in str(exc):
                    raise
                parsed = _parse_statement_func()(Path(file_path), bank, password=password)
    except PasswordProtectedError as exc:
        return await _fail_statement(db, statement, job_id, "parse", "password", str(exc))
    except PDFReadError as exc:
        return await _fail_statement(db, statement, job_id, "parse", "pdf", str(exc))
    except StatementParserError as exc:
        statement.status = "READY_FOR_REVIEW" if statement.file_type == "pdf" else "FAILED"
        statement.error_message = str(exc)
        statement.metadata_ = {
            **statement.metadata_,
            "parser": "pdf_text",
            "parse_warning": str(exc),
            "row_count": 0,
        }
        await _set_statement_job(
            db,
            statement,
            "parse",
            job_id=job_id,
            status="FAILED" if statement.status == "FAILED" else "COMPLETED",
            stage="parser",
            progress=100,
            detail=str(exc),
        )
        await db.commit()
        update_job_progress(job_id, job_type="parse", status=statement.status, stage="parser", progress=100, statement_id=statement.id, detail=str(exc))
        await notify_status_change(statement.id, statement.status)
        return {"statement_id": statement.id, "status": statement.status}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error parsing statement")
        return await _fail_statement(db, statement, job_id, "parse", "parser", f"Unexpected error: {exc}")

    is_ocr = parsed.metadata.get("parser") == "ocr"
    if is_ocr:
        statement.status = "OCR"
        await _set_statement_job(db, statement, "parse", job_id=job_id, status="STARTED", stage="ocr", progress=75)
        await db.commit()
        await notify_status_change(statement.id, "OCR")

    statement.metadata_ = {**statement.metadata_, **parsed.metadata}
    statement.status = "READY_FOR_REVIEW"

    new_txns: list[Transaction] = []
    for txn in parsed.transactions:
        tx_kwargs: dict = {
            "statement_id": statement.id,
            "row_number": txn.row_number,
            "txn_date": txn.txn_date,
            "value_date": txn.value_date,
            "narration": txn.narration,
            "reference_no": txn.reference_no,
            "debit": txn.debit,
            "credit": txn.credit,
            "balance": txn.balance,
        }
        if is_ocr and txn.ocr_confidence is not None:
            tx_kwargs["ocr_confidence"] = txn.ocr_confidence
        new_txns.append(Transaction(**tx_kwargs))

    db.add_all(new_txns)
    await db.flush()
    enrich_tx_ids = [tx.id for tx in new_txns]
    await _set_statement_job(db, statement, "parse", job_id=job_id, status="COMPLETED", stage="ready", progress=100)
    await db.commit()
    update_job_progress(job_id, job_type="parse", status="COMPLETED", stage="ready", progress=100, statement_id=statement.id)
    await notify_status_change(statement.id, statement.status)

    if enrich_tx_ids:
        await _auto_enrich_missing(db, job_id, statement.id, firm_id, enrich_tx_ids)

    return {"statement_id": statement.id, "status": statement.status, "transactions": len(new_txns)}


async def _transaction_ids(db: AsyncSession, statement_id: str) -> list[str]:
    result = await db.execute(
        select(Transaction.id)
        .where(Transaction.statement_id == statement_id)
        .order_by(Transaction.row_number)
    )
    return list(result.scalars().all())


async def _auto_enrich_missing(
    db: AsyncSession,
    parse_job_id: str,
    statement_id: str,
    firm_id: str,
    transaction_ids: list[str],
) -> None:
    if not transaction_ids:
        return
    await enrich_transactions_job(
        db,
        job_id=f"{parse_job_id}:auto-enrich",
        statement_id=statement_id,
        firm_id=firm_id,
        transaction_ids=transaction_ids,
        only_missing=True,
        limit=len(transaction_ids),
        force=False,
        auto=True,
    )


async def _fail_statement(
    db: AsyncSession,
    statement: Statement,
    job_id: str,
    job_type: str,
    stage: str,
    message: str,
) -> dict:
    statement.status = "FAILED"
    statement.error_message = message
    await _set_statement_job(db, statement, job_type, job_id=job_id, status="FAILED", stage=stage, progress=100, detail=message)
    await db.commit()
    update_job_progress(job_id, job_type=job_type, status="FAILED", stage=stage, progress=100, statement_id=statement.id, detail=message)
    await notify_status_change(statement.id, statement.status)
    return {"statement_id": statement.id, "status": statement.status}


async def enrich_transactions_job(
    db: AsyncSession,
    *,
    job_id: str,
    statement_id: str,
    firm_id: str,
    transaction_ids: list[str] | None = None,
    only_missing: bool = True,
    limit: int = 50,
    force: bool = False,
    auto: bool = False,
) -> dict:
    await set_rls_context(db, firm_id)
    statement = await db.get(Statement, statement_id)
    if not statement:
        update_job_progress(job_id, job_type="llm", status="FAILED", stage="missing", progress=100, statement_id=statement_id)
        return {"statement_id": statement_id, "updated": 0}

    llm_job = ((statement.metadata_ or {}).get("jobs") or {}).get("llm") or {}
    if llm_job.get("job_id") == job_id and llm_job.get("status") == "COMPLETED":
        usage = await summarize_usage(db, statement_id)
        update_job_progress(
            job_id,
            job_type="llm",
            status="COMPLETED",
            stage="done",
            progress=100,
            statement_id=statement_id,
            detail="Existing LLM enrichment reused for idempotent retry.",
            extra={"updated": 0, "auto": auto, "idempotent": True},
        )
        return {
            "statement_id": statement_id,
            "updated": 0,
            "usage": serialize_usage(usage),
            "items": [],
            "idempotent": True,
        }

    await _set_statement_job(db, statement, "llm", job_id=job_id, status="STARTED", stage="loading", progress=10)
    update_job_progress(job_id, job_type="llm", status="STARTED", stage="loading", progress=10, statement_id=statement_id)
    await db.commit()

    query = select(Transaction).where(Transaction.statement_id == statement_id)
    if transaction_ids:
        query = query.where(Transaction.id.in_(transaction_ids))
    if only_missing and not force:
        query = query.where(
            (Transaction.narration_clean.is_(None))
            | (Transaction.payment_mode.is_(None))
            | (Transaction.counterparty.is_(None))
            | (Transaction.confidence.is_(None))
        )

    result = await db.execute(query.order_by(Transaction.row_number).limit(limit))
    transactions = result.scalars().all()

    if force and transactions:
        stale_hashes = [content_hash_for_transaction(tx) for tx in transactions]
        await db.execute(delete(LLMCache).where(LLMCache.content_hash.in_(stale_hashes)))
        await db.flush()

    await _set_statement_job(db, statement, "llm", job_id=job_id, status="STARTED", stage="enriching", progress=40)
    update_job_progress(job_id, job_type="llm", status="STARTED", stage="enriching", progress=40, statement_id=statement_id)

    enrichments = await enrich_transactions_with_tracking(
        db, list(transactions), statement_id,
        client_id=statement.client_id,  # Task 17: constrain LLM to client's ledger list
    )
    by_id = {item.transaction_id: item for item in enrichments}
    for transaction in transactions:
        enrichment = by_id.get(transaction.id)
        if enrichment:
            apply_enrichment(transaction, enrichment)

    await _set_statement_job(db, statement, "llm", job_id=job_id, status="COMPLETED", stage="done", progress=100)
    await db.commit()
    usage = await summarize_usage(db, statement_id)
    update_job_progress(
        job_id,
        job_type="llm",
        status="COMPLETED",
        stage="done",
        progress=100,
        statement_id=statement_id,
        extra={"updated": len(enrichments), "auto": auto},
    )
    return {
        "statement_id": statement_id,
        "updated": len(enrichments),
        "usage": serialize_usage(usage),
        "items": [serialize_enrichment(item) for item in enrichments],
    }


async def export_statement_job(
    db: AsyncSession,
    *,
    job_id: str,
    export_id: str,
    statement_id: str,
    firm_id: str,
    fmt: str,
    company_name: str | None,
    bank_ledger_name: str | None,
    strict_reviewed_only: bool,
) -> dict:
    await set_rls_context(db, firm_id)
    job = await db.get(ExportJob, export_id)
    stmt = await db.get(Statement, statement_id)
    if not job or not stmt:
        update_job_progress(job_id, job_type="export", status="FAILED", stage="missing", progress=100, statement_id=statement_id, export_id=export_id)
        return {"export_id": export_id, "status": "missing"}

    if job.status == "READY":
        update_job_progress(
            job_id,
            job_type="export",
            status="COMPLETED",
            stage="ready",
            progress=100,
            statement_id=statement_id,
            export_id=export_id,
            detail="Existing ready export reused for idempotent retry.",
            extra={"idempotent": True},
        )
        return {"export_id": export_id, "status": "READY", "transaction_count": await _transaction_count(db, statement_id), "idempotent": True}

    if job.file_path and Path(job.file_path).exists():
        job.status = "READY"
        job.download_url = f"/v1/exports/{job.id}/download"
        if not job.expires_at:
            job.expires_at = utcnow() + timedelta(hours=EXPORT_TTL_HOURS)
        stmt.status = "EXPORTED"
        await db.commit()
        transaction_count = await _transaction_count(db, statement_id)
        update_job_progress(
            job_id,
            job_type="export",
            status="COMPLETED",
            stage="ready",
            progress=100,
            statement_id=statement_id,
            export_id=export_id,
            detail="Existing export file reused for idempotent retry.",
            extra={"transaction_count": transaction_count, "idempotent": True},
        )
        await notify_status_change(statement_id, "EXPORTED")
        return {"export_id": export_id, "status": "READY", "transaction_count": transaction_count, "idempotent": True}

    update_job_progress(job_id, job_type="export", status="STARTED", stage="rendering", progress=25, statement_id=statement_id, export_id=export_id)
    job.status = "RUNNING"
    await db.commit()

    try:
        payload, transaction_count = await build_export_content(
            db=db,
            stmt=stmt,
            fmt=fmt,
            company_name=company_name,
            bank_ledger_name=bank_ledger_name,
            strict_reviewed_only=strict_reviewed_only,
        )
        update_job_progress(job_id, job_type="export", status="STARTED", stage="writing", progress=75, statement_id=statement_id, export_id=export_id)
        file_path = write_export_file(statement_id, job.id, fmt, payload)
    except Exception as exc:  # noqa: BLE001
        job.status = "FAILED"
        job.error_message = str(exc)
        await db.commit()
        update_job_progress(job_id, job_type="export", status="FAILED", stage="failed", progress=100, statement_id=statement_id, export_id=export_id, detail=str(exc))
        raise

    job.status = "READY"
    job.file_path = str(file_path)
    job.download_url = f"/v1/exports/{job.id}/download"
    job.expires_at = utcnow() + timedelta(hours=EXPORT_TTL_HOURS)
    stmt.status = "EXPORTED"
    await db.commit()
    update_job_progress(
        job_id,
        job_type="export",
        status="COMPLETED",
        stage="ready",
        progress=100,
        statement_id=statement_id,
        export_id=export_id,
        extra={"transaction_count": transaction_count},
    )
    await notify_status_change(statement_id, "EXPORTED")
    return {"export_id": export_id, "status": "READY", "transaction_count": transaction_count}


async def _transaction_count(db: AsyncSession, statement_id: str) -> int:
    result = await db.execute(
        select(func.count(Transaction.id)).where(Transaction.statement_id == statement_id)
    )
    return int(result.scalar_one() or 0)
