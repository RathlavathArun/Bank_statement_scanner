import shutil
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import Client, Firm, Statement, Transaction
from statements.parser import StatementParserError, parse_statement
from statements.schemas import (
    TransactionItem, TransactionUpdate, BulkUpdateRequest, BulkUpdateResponse,
    StatementListItem, PaginatedTransactions, PaginatedStatements, StatementStatusUpdate,
)
from statements.websocket import notify_status_change

router = APIRouter(prefix="/v1/statements", tags=["statements"])

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_FIRM_NAME = "Default Firm"
DEFAULT_CLIENT_NAME = "Default Client"

# Allowed statement statuses
ALLOWED_STATUSES = {
    "UPLOADED", "PARSING", "OCR", "READY_FOR_REVIEW", "REVIEWED", "EXPORTED", "FAILED"
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
    except StatementParserError as exc:
        statement.status = "FAILED"
        statement.error_message = str(exc)
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
    bank_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all statements with pagination and filters."""
    query = select(Statement)
    
    if status:
        query = query.where(Statement.status == status)
    if bank_code:
        query = query.where(Statement.bank_code == bank_code)
    
    # Get total count
    count_result = await db.execute(select(func.count(Statement.id)).select_from(Statement))
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
            client_id=stmt.client_id,
            file_type=stmt.file_type,
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
        query = query.where(Transaction.txn_date >= date_from)
    if date_to:
        query = query.where(Transaction.txn_date <= date_to)
    
    if search:
        query = query.where(Transaction.narration.ilike(f"%{search}%"))
    
    # Get total count
    count_result = await db.execute(
        select(func.count(Transaction.id)).select_from(query.subquery())
    )
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
    
    # Apply updates (only present fields)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tx, field, value)
    
    await db.commit()
    await db.refresh(tx)
    
    return {
        "success": True,
        "data": TransactionItem.model_validate(tx).model_dump()
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
        for field, value in item.model_dump(exclude_unset=True, exclude={"id"}).items():
            setattr(tx, field, value)
        
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
    )
