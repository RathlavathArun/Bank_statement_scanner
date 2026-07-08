"""Celery tasks for parser/OCR, LLM enrichment, and export work."""
from __future__ import annotations

import asyncio

from core.celery_app import celery_app
from db.database import async_session, engine
from statements.processing import enrich_transactions_job, export_statement_job, process_statement_job


async def _run_with_fresh_db_session(job):
    """Run one Celery job without leaking asyncpg connections across loops.

    Celery invokes these synchronous task functions repeatedly in the same
    worker process, while ``asyncio.run`` creates a fresh event loop each time.
    Disposing the async engine before that loop closes prevents pooled asyncpg
    connections from being reused by the next task's different event loop.
    """
    try:
        async with async_session() as db:
            return await job(db)
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="statements.process_statement")
def process_statement_task(
    self,
    statement_id: str,
    file_path: str,
    bank: str | None,
    password: str | None,
    firm_id: str,
) -> dict:
    async def run(db) -> dict:
        return await process_statement_job(
            db,
            job_id=self.request.id,
            statement_id=statement_id,
            file_path=file_path,
            bank=bank,
            password=password,
            firm_id=firm_id,
        )

    return asyncio.run(_run_with_fresh_db_session(run))


@celery_app.task(bind=True, name="statements.enrich_transactions")
def enrich_transactions_task(
    self,
    statement_id: str,
    firm_id: str,
    transaction_ids: list[str] | None = None,
    only_missing: bool = True,
    limit: int = 50,
    force: bool = False,
) -> dict:
    async def run(db) -> dict:
        return await enrich_transactions_job(
            db,
            job_id=self.request.id,
            statement_id=statement_id,
            firm_id=firm_id,
            transaction_ids=transaction_ids,
            only_missing=only_missing,
            limit=limit,
            force=force,
        )

    return asyncio.run(_run_with_fresh_db_session(run))


@celery_app.task(bind=True, name="statements.export_statement")
def export_statement_task(
    self,
    export_id: str,
    statement_id: str,
    firm_id: str,
    fmt: str,
    company_name: str | None,
    bank_ledger_name: str | None,
    strict_reviewed_only: bool,
) -> dict:
    async def run(db) -> dict:
        return await export_statement_job(
            db,
            job_id=self.request.id,
            export_id=export_id,
            statement_id=statement_id,
            firm_id=firm_id,
            fmt=fmt,
            company_name=company_name,
            bank_ledger_name=bank_ledger_name,
            strict_reviewed_only=strict_reviewed_only,
        )

    return asyncio.run(_run_with_fresh_db_session(run))
