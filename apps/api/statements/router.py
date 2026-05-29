import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Client, Firm, Statement, Transaction
from statements.parser import PDFReadError, StatementParserError, parse_statement
from statements.ledger_memory import (
    remember_ledger_mapping,
    serialize_suggestion,
    suggest_ledgers,
)
from statements.llm_enrichment import (
    apply_enrichment,
    enrich_transactions_with_tracking,
    serialize_enrichment,
)
from statements.llm_tracking import serialize_usage, summarize_usage
from statements.schemas import (
    TransactionItem, TransactionUpdate, BulkUpdateRequest, BulkUpdateResponse,
    StatementListItem, PaginatedTransactions, PaginatedStatements, StatementStatusUpdate,
    EnrichTransactionsRequest,
)
from statements.websocket import notify_status_change

router = APIRouter(prefix="/v1/statements", tags=["statements"])

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FIRM_NAME = "Default Firm"
DEFAULT_CLIENT_NAME = "Default Client"

# Allowed statement statuses
ALLOWED_STATUSES = {
    "UPLOADED", "PARSING", "OCR", "READY_FOR_REVIEW", "REVIEWED", "EXPORTED", "FAILED", "PARSE_ERROR"
}


def file_type_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"pdf", "csv", "xlsx", "xls"}:
        return suffix
    if suffix in {"jpg", "jpeg", "png", "webp"}:
        return "image"
    return suffix or "unknown"


def money(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


async def get_or_create_default_client(db: AsyncSession) -> Client:
    result = await db.execute(select(Client).where(Client.name == DEFAULT_CLIENT_NAME))
    client = result.scalar_one_or_none()
    if client:
        return client

    firm = Firm(name=DEFAULT_FIRM_NAME)
    db.add(firm)
    await db.flush()

    client = Client(firm_id=firm.id, name=DEFAULT_CLIENT_NAME)
    db.add(client)
    await db.flush()

    return client


def serialize_statement(statement: Statement) -> dict:
    return {
        "id": statement.id,
        "filename": statement.metadata_.get("original_filename"),
        "bank": statement.bank_code,
        "file_type": statement.file_type,
        "status": statement.status,
        "path": statement.file_url,
        "error": statement.error_message,
    }


def serialize_transaction(transaction: Transaction) -> dict:
    return {
        "id": transaction.id,
        "date": transaction.txn_date.isoformat(),
        "value_date": transaction.value_date.isoformat() if transaction.value_date else None,
        "description": transaction.narration,
        "reference_no": transaction.reference_no,
        "debit": money(transaction.debit),
        "credit": money(transaction.credit),
        "balance": money(transaction.balance),
    }


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    original_filename = file.filename or "statement"
    client = await get_or_create_default_client(db)

    statement = Statement(
        client_id=client.id,
        file_url="",
        file_type=file_type_for(original_filename),
        bank_code=bank,
        status="UPLOADED",
        metadata_={"original_filename": original_filename},
    )
    db.add(statement)
    await db.flush()

    safe_filename = Path(original_filename).name
    file_path = UPLOAD_DIR / f"{statement.id}-{safe_filename}"
    statement.file_url = str(file_path)

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    statement.status = "PARSING"
    try:
        parsed = parse_statement(file_path, bank)
    except PDFReadError as exc:
        statement.status = "FAILED"
        statement.error_message = str(exc)
    except StatementParserError as exc:
        statement.status = "READY_FOR_REVIEW" if statement.file_type == "pdf" else "FAILED"
        statement.error_message = str(exc)
        statement.metadata_ = {
            **statement.metadata_,
            "parser": "pdf_text",
            "parse_warning": str(exc),
            "row_count": 0,
        }
    else:
        statement.metadata_ = {
            **statement.metadata_,
            **parsed.metadata,
        }
        statement.status = "READY_FOR_REVIEW"
        db.add_all(
            [
                Transaction(
                    statement_id=statement.id,
                    row_number=txn.row_number,
                    txn_date=txn.txn_date,
                    value_date=txn.value_date,
                    narration=txn.narration,
                    reference_no=txn.reference_no,
                    debit=txn.debit,
                    credit=txn.credit,
                    balance=txn.balance,
                )
                for txn in parsed.transactions
            ]
        )
    await db.flush()
    await notify_status_change(statement.id, statement.status)

    return {
        "success": True,
        "message": "Statement uploaded successfully",
        "data": serialize_statement(statement),
    }


@router.get("/{statement_id}/status")
async def get_statement_status(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    return {
        "success": True,
        "message": "Statement status fetched successfully",
        "data": serialize_statement(statement),
    }


@router.get("/{statement_id}/result")
async def get_statement_result(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    statement = await db.get(Statement, statement_id)

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    result = await db.execute(
        select(Transaction)
        .where(Transaction.statement_id == statement_id)
        .order_by(Transaction.row_number)
    )
    transactions = result.scalars().all()

    return {
        "success": True,
        "message": "Statement parsed successfully",
        "data": {
            **serialize_statement(statement),
            "transactions": [serialize_transaction(txn) for txn in transactions],
        },
    }


# ─────────────────────────────────────────────────────────────
# PHASE 2 NEW ENDPOINTS
# ─────────────────────────────────────────────────────────────

@router.get("", response_model=dict)
async def list_statements(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    bank_id: Optional[str] = None,
    bank_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all statements with pagination and filters."""
    query = select(Statement)
    
    if status:
        query = query.where(Statement.status == status)
    selected_bank = bank_id or bank_code
    if selected_bank:
        query = query.where(Statement.bank_code == selected_bank)
    
    # Get total count
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()
    
    # Get paginated results
    query = query.order_by(Statement.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    statements = result.scalars().all()
    
    # Count transactions per statement
    items = []
    for stmt in statements:
        tx_count_result = await db.execute(
            select(func.count(Transaction.id)).where(Transaction.statement_id == stmt.id)
        )
        tx_count = tx_count_result.scalar_one() or 0
        
        items.append(StatementListItem(
            id=stmt.id,
            filename=stmt.metadata_.get("original_filename") or Path(stmt.file_url).name or "statement",
            client_id=stmt.client_id,
            file_type=stmt.file_type,
            bank_id=stmt.bank_code,
            bank_code=stmt.bank_code,
            account_number=stmt.account_number,
            account_holder=stmt.account_holder,
            period_start=stmt.period_start.isoformat() if stmt.period_start else None,
            period_end=stmt.period_end.isoformat() if stmt.period_end else None,
            status=stmt.status,
            error_message=stmt.error_message,
            created_at=stmt.created_at,
            transaction_count=tx_count,
        ))
    
    pages = -(-total // size)  # Ceiling division
    
    return {
        "success": True,
        "data": PaginatedStatements(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages,
        ).model_dump()
    }


@router.get("/{statement_id}/transactions", response_model=dict)
async def list_transactions(
    statement_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    tx_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List transactions for a statement with filtering."""
    # Verify statement exists
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    query = select(Transaction).where(Transaction.statement_id == statement_id)
    
    # Apply filters
    if tx_type:
        tx_type = tx_type.upper()
        if tx_type == "DEBIT":
            query = query.where(Transaction.debit.isnot(None))
        elif tx_type == "CREDIT":
            query = query.where(Transaction.credit.isnot(None))
    
    if date_from:
        query = query.where(Transaction.txn_date >= datetime.strptime(date_from, "%Y-%m-%d").date())
    if date_to:
        query = query.where(Transaction.txn_date <= datetime.strptime(date_to, "%Y-%m-%d").date())
    
    if search:
        query = query.where(Transaction.narration.ilike(f"%{search}%"))
    
    # Get total count
    count_query = query.order_by(None).subquery()
    count_result = await db.execute(select(func.count()).select_from(count_query))
    total = count_result.scalar_one()
    
    # Get paginated results
    query = query.order_by(Transaction.txn_date).offset((page - 1) * size).limit(size)
    result = await db.execute(query)
    transactions = result.scalars().all()
    
    items = [TransactionItem.model_validate(txn) for txn in transactions]
    pages = -(-total // size) if total > 0 else 1
    
    return {
        "success": True,
        "data": PaginatedTransactions(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages,
        ).model_dump()
    }


@router.put("/{statement_id}/transactions/{transaction_id}", response_model=dict)
async def update_transaction(
    statement_id: str,
    transaction_id: str,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a single transaction."""
    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.statement_id == statement_id,
        )
    )
    tx = result.scalar_one_or_none()
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    stmt = await db.get(Statement, statement_id)
    
    # Apply updates (only present fields)
    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(tx, field, value)

    if stmt and updates.get("confirmed_ledger"):
        await remember_ledger_mapping(
            db=db,
            transaction=tx,
            ledger_name=updates["confirmed_ledger"],
            client_id=stmt.client_id,
        )
    
    await db.commit()
    await db.refresh(tx)
    
    return {
        "success": True,
        "data": TransactionItem.model_validate(tx).model_dump()
    }


@router.get("/{statement_id}/transactions/{transaction_id}/ledger-suggestions", response_model=dict)
async def get_ledger_suggestions(
    statement_id: str,
    transaction_id: str,
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Suggest ledgers from learned client mappings and optional Qdrant memory."""
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.statement_id == statement_id,
        )
    )
    tx = result.scalar_one_or_none()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    suggestions = await suggest_ledgers(db, tx, stmt.client_id, limit=limit)
    return {
        "success": True,
        "data": {
            "transaction_id": tx.id,
            "suggestions": [serialize_suggestion(item) for item in suggestions],
        },
    }


@router.post("/{statement_id}/transactions/enrich", response_model=dict)
async def enrich_statement_transactions(
    statement_id: str,
    body: EnrichTransactionsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Enrich transaction narrations with Claude when configured, otherwise local rules."""
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")

    query = select(Transaction).where(Transaction.statement_id == statement_id)
    if body.transaction_ids:
        query = query.where(Transaction.id.in_(body.transaction_ids))
    if body.only_missing:
        query = query.where(
            (Transaction.narration_clean.is_(None))
            | (Transaction.payment_mode.is_(None))
            | (Transaction.counterparty.is_(None))
            | (Transaction.confidence.is_(None))
        )

    result = await db.execute(query.order_by(Transaction.row_number).limit(body.limit))
    transactions = result.scalars().all()
    enrichments = await enrich_transactions_with_tracking(db, list(transactions), statement_id)
    by_id = {item.transaction_id: item for item in enrichments}

    for transaction in transactions:
        enrichment = by_id.get(transaction.id)
        if enrichment:
            apply_enrichment(transaction, enrichment)

    await db.commit()
    usage = await summarize_usage(db, statement_id)

    return {
        "success": True,
        "data": {
            "statement_id": statement_id,
            "updated": len(enrichments),
            "usage": serialize_usage(usage),
            "items": [serialize_enrichment(item) for item in enrichments],
        },
    }


@router.get("/{statement_id}/llm-usage", response_model=dict)
async def get_statement_llm_usage(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return LLM cache/cost totals for a statement."""
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")

    return {
        "success": True,
        "data": {
            "statement_id": statement_id,
            "usage": serialize_usage(await summarize_usage(db, statement_id)),
        },
    }


@router.post("/{statement_id}/transactions/bulk-update", response_model=dict)
async def bulk_update_transactions(
    statement_id: str,
    body: BulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bulk update multiple transactions in a single transaction."""
    # Verify statement exists
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    updated = 0
    failed = []
    
    for item in body.updates:
        result = await db.execute(
            select(Transaction).where(
                Transaction.id == item.id,
                Transaction.statement_id == statement_id,
            )
        )
        tx = result.scalar_one_or_none()
        
        if not tx:
            failed.append({"id": item.id, "reason": "Transaction not found"})
            continue
        
        # Apply updates
        updates = item.model_dump(exclude_unset=True, exclude={"id"})
        for field, value in updates.items():
            setattr(tx, field, value)

        if updates.get("confirmed_ledger"):
            await remember_ledger_mapping(
                db=db,
                transaction=tx,
                ledger_name=updates["confirmed_ledger"],
                client_id=stmt.client_id,
            )
        
        updated += 1
    
    await db.commit()
    
    return {
        "success": True,
        "data": BulkUpdateResponse(updated=updated, failed=failed).model_dump()
    }


@router.patch("/{statement_id}/status", response_model=dict)
async def update_statement_status(
    statement_id: str,
    body: StatementStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update statement status."""
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    if body.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(ALLOWED_STATUSES)}"
        )
    
    stmt.status = body.status
    await db.commit()
    await db.refresh(stmt)
    
    # Notify WebSocket watchers
    await notify_status_change(statement_id, body.status)
    
    return {
        "success": True,
        "data": {
            "statement_id": stmt.id,
            "status": stmt.status,
        }
    }


@router.get("/{statement_id}/file", response_class=FileResponse)
async def get_statement_file(
    statement_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Download the uploaded statement file."""
    stmt = await db.get(Statement, statement_id)
    if not stmt:
        raise HTTPException(status_code=404, detail="Statement not found")
    
    file_path = Path(stmt.file_url)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=stmt.metadata_.get("original_filename", "statement"),
        media_type="application/pdf" if stmt.file_type == "pdf" else None,
    )
